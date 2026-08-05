<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
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

onMounted(() => {
  config.value = normalizeConfig(props.initialConfig || {})
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
        <VRow>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.cd2_grpc_addr"
              label="CD2 gRPC 地址"
              placeholder="host:port"
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.cd2_token"
              label="CD2 访问令牌"
              type="password"
              autocomplete="new-password"
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.cd2_plugin_staging_root"
              label="插件侧 CD2 staging 根目录"
              placeholder="/SSD/云盘/l"
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.cd2_dest_root"
              label="CD2 云端目标根目录"
              placeholder="/云盘/影视库"
            />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField v-model="config.pending_import_cron" label="待入库 CRON" />
          </VCol>
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
      </VWindowItem>

      <VWindowItem value="external">
        <VRow>
          <VCol cols="12" md="5">
            <VTextField v-model="config.catchup_base_url" label="追更 Emby 地址" />
          </VCol>
          <VCol cols="12" md="3">
            <VTextField v-model="config.catchup_page_id" label="追更 PageId" />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField
              v-model="config.catchup_token"
              label="追更 Token"
              type="password"
              autocomplete="new-password"
            />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField v-model="config.scan_base_url" label="扫库系统地址" />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField v-model="config.scan_username" label="扫库账号" />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField
              v-model="config.scan_password"
              label="扫库密码"
              type="password"
              autocomplete="new-password"
            />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField v-model="config.scan_setting_name" label="扫库配置名" />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField v-model="config.scan_target_name" label="扫库节点名" />
          </VCol>
          <VCol cols="12" md="6">
            <VTextField
              v-model="config.scan_callback_secret"
              label="Emby 扫库回调密钥"
              type="password"
              autocomplete="new-password"
            />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField v-model="config.scan_callback_server_id" label="回调服务器 ID（可选）" />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField v-model="config.scan_callback_task_id" label="回调任务 ID（可选）" />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField v-model="config.scan_callback_task_name" label="回调任务名称（可选）" />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField
              v-model.number="config.scan_callback_timeout"
              label="扫库回调等待超时（秒）"
              type="number"
            />
          </VCol>
        </VRow>
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
