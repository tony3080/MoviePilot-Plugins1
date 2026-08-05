<script setup>
import { onMounted, ref, watch } from 'vue'

const props = defineProps({
  api: {
    type: Object,
    default: () => ({}),
  },
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['save', 'close'])

const defaultRoutes = [
  {
    name: 'UP',
    prefix: '/MP',
    link_roots: {
      movie: '/MP/电影UP',
      series: '/MP/剧集UP',
      default: '',
    },
    enabled: true,
  },
  {
    name: 'SSD',
    prefix: '/SSD',
    link_roots: {
      movie: '',
      series: '',
      default: '/SSD/云盘/l',
    },
    enabled: true,
  },
]

const defaults = {
  enabled: false,
  database_filename: 'rssallinone.db',
  inventory_root: '/SSD/云盘/strm/影视库',
  source_routes: defaultRoutes,
  cd2_grpc_addr: '',
  cd2_token: '',
  cd2_plugin_staging_root: '/SSD/云盘/l',
  cd2_dest_root: '',
  pending_import_cron: '0 1 * * *',
  cd2_discovery_timeout: 180,
  cd2_card_timeout: 7200,
  cd2_poll_interval: 10,
  cd2_transfer_grace: 20,
  cd2_risk_cooldown: 1800,
  cd2_risk_retry_limit: 3,
  catchup_base_url: '',
  catchup_page_id: '',
  catchup_token: '',
  scan_base_url: '',
  scan_username: '',
  scan_password: '',
  scan_setting_name: '',
  scan_target_name: '',
  scan_callback_secret: '',
  scan_callback_server_id: '',
  scan_callback_task_id: '',
  scan_callback_task_name: '',
  scan_callback_timeout: 7200,
}

const config = ref({ ...defaults })
const section = ref('general')
const catchupState = ref(null)
const scanState = ref(null)
const catchupBusy = ref(false)
const scanBusy = ref(false)
const externalMessage = ref('')
const externalMessageType = ref('info')

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function parseStructured(value, fallback) {
  if (typeof value !== 'string') return value ?? fallback
  try {
    return JSON.parse(value)
  } catch {
    return fallback
  }
}

function normalizeRoute(route = {}, index = 0) {
  return {
    name: route.name || `路由${index + 1}`,
    prefix: route.prefix || '',
    link_roots: {
      movie: route.link_roots?.movie || '',
      series: route.link_roots?.series || '',
      default: route.link_roots?.default || '',
    },
    enabled: route.enabled !== false,
  }
}

function normalizeConfig(initial = {}) {
  const next = {
    ...clone(defaults),
    ...clone(initial),
  }
  const routeValue = parseStructured(initial.source_routes, defaultRoutes)
  const routes = Array.isArray(routeValue) ? routeValue : defaultRoutes
  next.source_routes = routes.map(normalizeRoute)
  delete next.category_groups
  return next
}

function save() {
  emit('save', clone(config.value))
}

function addRoute() {
  config.value.source_routes.push(normalizeRoute({}, config.value.source_routes.length))
}

function removeRoute(index) {
  config.value.source_routes.splice(index, 1)
}

function unwrap(response) {
  return response?.data ?? response
}

function stateColor(state) {
  if (state === true) return 'success'
  if (state === false) return 'error'
  return 'default'
}

function catchupConfigReady() {
  return Boolean(
    String(config.value.catchup_base_url || '').trim()
    && String(config.value.catchup_page_id || '').trim()
    && String(config.value.catchup_token || '').trim(),
  )
}

function scanConfigReady() {
  return Boolean(
    String(config.value.scan_base_url || '').trim()
    && String(config.value.scan_username || '').trim()
    && String(config.value.scan_password || '').trim()
    && String(config.value.scan_setting_name || '').trim()
    && String(config.value.scan_target_name || '').trim(),
  )
}

async function controlCatchup(forceRead = false) {
  if (!catchupConfigReady()) {
    catchupState.value = null
    externalMessageType.value = 'warning'
    externalMessage.value = '请先填写完整的追更 Emby 地址、PageId 和 Token'
    return
  }
  catchupBusy.value = true
  externalMessage.value = ''
  try {
    const action = forceRead || catchupState.value === null ? 'read' : 'toggle'
    const result = unwrap(await props.api.post(
      'plugin/RssAllInOne/external/catchup/control',
      {
        action,
        catchup_base_url: config.value.catchup_base_url,
        catchup_page_id: config.value.catchup_page_id,
        catchup_token: config.value.catchup_token,
      },
    )) || {}
    if (!result.success) throw new Error(result.message || '追更开关操作失败')
    catchupState.value = Boolean(result.enabled)
    externalMessageType.value = 'success'
    externalMessage.value = result.message || '追更状态读取完成'
  } catch (error) {
    catchupState.value = null
    externalMessageType.value = 'error'
    externalMessage.value = error?.message || '追更开关操作失败'
  } finally {
    catchupBusy.value = false
  }
}

async function controlScan(forceRead = false) {
  if (!scanConfigReady()) {
    scanState.value = null
    externalMessageType.value = 'warning'
    externalMessage.value = '请先填写完整的 SA 地址、账号、密码、配置名和节点名'
    return
  }
  scanBusy.value = true
  externalMessage.value = ''
  try {
    const action = forceRead || scanState.value === null ? 'read' : 'toggle'
    const result = unwrap(await props.api.post(
      'plugin/RssAllInOne/external/scan/control',
      {
        action,
        scan_base_url: config.value.scan_base_url,
        scan_username: config.value.scan_username,
        scan_password: config.value.scan_password,
        scan_setting_name: config.value.scan_setting_name,
        scan_target_name: config.value.scan_target_name,
      },
    )) || {}
    if (!result.success) throw new Error(result.message || 'SA 扫库开关操作失败')
    scanState.value = Boolean(result.enabled)
    externalMessageType.value = 'success'
    externalMessage.value = result.message || 'SA 扫库状态读取完成'
  } catch (error) {
    scanState.value = null
    externalMessageType.value = 'error'
    externalMessage.value = error?.message || 'SA 扫库开关操作失败'
  } finally {
    scanBusy.value = false
  }
}

watch(
  () => [
    config.value.catchup_base_url,
    config.value.catchup_page_id,
    config.value.catchup_token,
  ],
  () => { catchupState.value = null },
)

watch(
  () => [
    config.value.scan_base_url,
    config.value.scan_username,
    config.value.scan_password,
    config.value.scan_setting_name,
    config.value.scan_target_name,
  ],
  () => { scanState.value = null },
)

onMounted(async () => {
  config.value = normalizeConfig(props.initialConfig || {})
  const reads = []
  if (catchupConfigReady()) reads.push(controlCatchup(true))
  if (scanConfigReady()) reads.push(controlScan(true))
  await Promise.allSettled(reads)
})
</script>

<template>
  <div class="config-root">
    <VToolbar density="comfortable" color="transparent">
      <div class="text-h6 ms-3">RSS一条龙配置</div>
      <VSpacer />
      <VTooltip text="保存">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-content-save"
            variant="text"
            color="primary"
            aria-label="保存"
            @click="save"
          />
        </template>
      </VTooltip>
      <VTooltip text="关闭">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-close"
            variant="text"
            aria-label="关闭"
            @click="emit('close')"
          />
        </template>
      </VTooltip>
    </VToolbar>
    <VDivider />

    <VTabs v-model="section" density="compact" color="primary" class="config-tabs">
      <VTab value="general">常规</VTab>
      <VTab value="cd2">CloudDrive2</VTab>
      <VTab value="external">外部联动</VTab>
    </VTabs>

    <VWindow v-model="section" class="config-window">
      <VWindowItem value="general">
        <VRow>
          <VCol cols="12" md="4">
            <VSwitch v-model="config.enabled" label="启用插件" color="primary" />
          </VCol>
          <VCol cols="12" md="8">
            <VTextField
              v-model="config.database_filename"
              label="状态数据库文件名"
              hint="保存在 MoviePilot 分配的插件数据目录"
              persistent-hint
            />
          </VCol>
          <VCol cols="12">
            <VTextField
              v-model="config.inventory_root"
              label="最终媒体库根目录"
              placeholder="/SSD/云盘/strm/影视库"
            />
          </VCol>
          <VCol cols="12">
            <div class="config-section-header">
              <div class="text-subtitle-2">源路径路由</div>
              <VBtn
                size="small"
                variant="text"
                prepend-icon="mdi-plus"
                @click="addRoute"
              >
                添加路由
              </VBtn>
            </div>
            <VTable density="compact" class="route-table">
              <thead>
                <tr>
                  <th>启用</th>
                  <th>名称</th>
                  <th>源路径前缀</th>
                  <th>电影硬链接根目录</th>
                  <th>剧集硬链接根目录</th>
                  <th>默认硬链接根目录</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(route, index) in config.source_routes" :key="`${route.name}-${index}`">
                  <td><VSwitch v-model="route.enabled" density="compact" hide-details /></td>
                  <td><VTextField v-model="route.name" density="compact" hide-details /></td>
                  <td><VTextField v-model="route.prefix" density="compact" hide-details /></td>
                  <td><VTextField v-model="route.link_roots.movie" density="compact" hide-details /></td>
                  <td><VTextField v-model="route.link_roots.series" density="compact" hide-details /></td>
                  <td><VTextField v-model="route.link_roots.default" density="compact" hide-details /></td>
                  <td>
                    <VTooltip text="删除路由">
                      <template #activator="{ props: tooltipProps }">
                        <VBtn
                          v-bind="tooltipProps"
                          icon="mdi-delete-outline"
                          size="small"
                          variant="text"
                          color="error"
                          aria-label="删除路由"
                          @click="removeRoute(index)"
                        />
                      </template>
                    </VTooltip>
                  </td>
                </tr>
              </tbody>
            </VTable>
          </VCol>
        </VRow>
      </VWindowItem>

      <VWindowItem value="cd2">
        <div class="settings-section-title">CloudDrive2 连接与路径</div>
        <VRow>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.cd2_grpc_addr"
              label="CD2 gRPC 地址 *"
              placeholder="192.168.110.31:19798"
              hint="只填写 IP:端口，不包含 http://"
              persistent-hint
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.cd2_token"
              label="CD2 访问令牌 *"
              type="password"
              autocomplete="new-password"
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.cd2_plugin_staging_root"
              label="插件侧 CD2 staging 根目录 *"
              placeholder="/SSD/云盘/l"
              hint="插件创建硬链接、CD2 自动备份所监控的本地根目录"
              persistent-hint
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.cd2_dest_root"
              label="CD2 上传任务目标根目录 *"
              placeholder="/云盘/影视库"
              hint="用于和 CD2 上传任务的完整 destPath 精确匹配"
              persistent-hint
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.pending_import_cron"
              label="待入库 CRON *"
              placeholder="30 1 * * *"
              hint="五段 CRON；只在存在待入库卡片时启动处理"
              persistent-hint
            />
          </VCol>
        </VRow>

        <VExpansionPanels variant="accordion" class="advanced-panels">
          <VExpansionPanel title="CD2 高级监控参数">
            <VExpansionPanelText>
              <VRow>
                <VCol cols="12" md="4">
                  <VTextField
                    v-model.number="config.cd2_discovery_timeout"
                    label="上传任务发现超时（秒）"
                    type="number"
                  />
                </VCol>
                <VCol cols="12" md="4">
                  <VTextField
                    v-model.number="config.cd2_card_timeout"
                    label="单卡最终超时（秒）"
                    type="number"
                  />
                </VCol>
                <VCol cols="12" md="4">
                  <VTextField
                    v-model.number="config.cd2_poll_interval"
                    label="CD2 活跃轮询（秒）"
                    type="number"
                  />
                </VCol>
                <VCol cols="12" md="4">
                  <VTextField
                    v-model.number="config.cd2_transfer_grace"
                    label="真实传输观察期（秒）"
                    type="number"
                  />
                </VCol>
                <VCol cols="12" md="4">
                  <VTextField
                    v-model.number="config.cd2_risk_cooldown"
                    label="风控暂停时间（秒）"
                    type="number"
                  />
                </VCol>
                <VCol cols="12" md="4">
                  <VTextField
                    v-model.number="config.cd2_risk_retry_limit"
                    label="连续风控停止阈值"
                    type="number"
                  />
                </VCol>
              </VRow>
            </VExpansionPanelText>
          </VExpansionPanel>
        </VExpansionPanels>
      </VWindowItem>

      <VWindowItem value="external">
        <VAlert
          v-if="externalMessage"
          :type="externalMessageType"
          variant="tonal"
          density="compact"
          closable
          class="mb-4"
          @click:close="externalMessage = ''"
        >
          {{ externalMessage }}
        </VAlert>

        <div class="settings-title-row">
          <div class="settings-section-title">追更控制（Emby）</div>
          <VTooltip :text="catchupState === null ? '读取追更状态' : `点击${catchupState ? '关闭' : '开启'}追更`">
            <template #activator="{ props: tooltipProps }">
              <VBtn
                v-bind="tooltipProps"
                :color="stateColor(catchupState)"
                variant="tonal"
                size="small"
                :loading="catchupBusy"
                @click="controlCatchup(false)"
              >
                <VIcon
                  icon="mdi-circle"
                  :color="stateColor(catchupState)"
                  size="12"
                  class="me-2"
                />
                追更：{{ catchupState === null ? '检测' : (catchupState ? '开启' : '关闭') }}
              </VBtn>
            </template>
          </VTooltip>
        </div>
        <VRow>
          <VCol cols="12" md="5">
            <VTextField
              v-model="config.catchup_base_url"
              label="追更 Emby 地址 *"
              placeholder="http://192.168.110.31:8096"
            />
          </VCol>
          <VCol cols="12" md="3">
            <VTextField
              v-model="config.catchup_page_id"
              label="追更插件 PageId *"
              placeholder="63c322:Settings"
            />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField
              v-model="config.catchup_token"
              label="追更 Emby Token *"
              type="password"
              autocomplete="new-password"
            />
          </VCol>
        </VRow>

        <VDivider class="settings-divider" />
        <div class="settings-title-row">
          <div class="settings-section-title">外部扫库控制（SA）</div>
          <VTooltip :text="scanState === null ? '读取 SA 扫库状态' : `点击${scanState ? '关闭' : '开启'} SA 扫库`">
            <template #activator="{ props: tooltipProps }">
              <VBtn
                v-bind="tooltipProps"
                :color="stateColor(scanState)"
                variant="tonal"
                size="small"
                :loading="scanBusy"
                @click="controlScan(false)"
              >
                <VIcon
                  icon="mdi-circle"
                  :color="stateColor(scanState)"
                  size="12"
                  class="me-2"
                />
                扫库：{{ scanState === null ? '检测' : (scanState ? '开启' : '关闭') }}
              </VBtn>
            </template>
          </VTooltip>
        </div>
        <VRow>
          <VCol cols="12" md="4">
            <VTextField
              v-model="config.scan_base_url"
              label="SA 系统地址 *"
              placeholder="http://192.168.110.31:8095"
            />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField v-model="config.scan_username" label="SA 登录账号 *" />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField
              v-model="config.scan_password"
              label="SA 登录密码 *"
              type="password"
              autocomplete="new-password"
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.scan_setting_name"
              label="SA 扫库配置名 *"
              placeholder="emby_server"
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.scan_target_name"
              label="SA 扫库节点名 *"
              hint="必须和 SA 配置中的节点名称完全一致"
              persistent-hint
            />
          </VCol>
        </VRow>

        <VDivider class="settings-divider" />
        <div class="settings-section-title">Emby 扫库完成回调</div>
        <VRow>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.scan_callback_secret"
              label="回调密钥 *"
              type="password"
              autocomplete="new-password"
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.scan_callback_server_id"
              label="Emby 服务器 ID *"
              hint="用于确认回调来自本轮刷新的目标 Emby"
              persistent-hint
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.scan_callback_task_id"
              label="Emby 扫库任务 ID"
              hint="任务 ID 与任务名称至少填写一项；优先使用 ID"
              persistent-hint
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.scan_callback_task_name"
              label="Emby 扫库任务名称"
              hint="任务 ID 与任务名称至少填写一项"
              persistent-hint
            />
          </VCol>
        </VRow>

        <VExpansionPanels variant="accordion" class="advanced-panels">
          <VExpansionPanel title="回调高级参数">
            <VExpansionPanelText>
              <VRow>
                <VCol cols="12" md="4">
                  <VTextField
                    v-model.number="config.scan_callback_timeout"
                    label="扫库回调等待超时（秒）"
                    type="number"
                  />
                </VCol>
              </VRow>
            </VExpansionPanelText>
          </VExpansionPanel>
        </VExpansionPanels>
      </VWindowItem>
    </VWindow>
  </div>
</template>

<style scoped>
.config-root {
  min-width: 0;
}

.config-tabs {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.config-window {
  padding: 16px;
}

.config-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.settings-section-title {
  margin: 2px 0 14px;
  font-size: 14px;
  font-weight: 700;
}

.settings-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.settings-divider {
  margin: 10px 0 18px;
}

.advanced-panels {
  margin-top: 8px;
}

.route-table {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 6px;
  overflow-x: auto;
}

.route-table th {
  white-space: nowrap;
}

.route-table td {
  min-width: 150px;
  padding: 6px;
}

.route-table td:first-child,
.route-table td:last-child {
  min-width: 64px;
  width: 64px;
}
</style>
