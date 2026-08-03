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
  qb_refresh_cron: '*/10 * * * *',
  inventory_root: '/SSD/云盘/strm/影视库',
  source_routes: defaultRoutes,
  cd2_grpc_addr: '',
  cd2_token: '',
  catchup_base_url: '',
  catchup_page_id: '',
  catchup_token: '',
  scan_base_url: '',
  scan_username: '',
  scan_password: '',
  scan_setting_name: '',
  scan_target_name: '',
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
          <VCol cols="12" md="4">
            <VTextField
              v-model="config.qb_refresh_cron"
              label="QB 只读刷新 CRON"
              placeholder="*/10 * * * *"
            />
          </VCol>
          <VCol cols="12" md="8">
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
