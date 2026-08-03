<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import RssTaskEditor from './RssTaskEditor.vue'

const props = defineProps({
  api: {
    type: Object,
    default: () => ({}),
  },
})

const activeTab = ref('overview')
const vtTab = ref('rss_tasks')
const loading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const overview = ref({ plugin: {}, counts: {}, capabilities: {} })
const rows = ref([])
const total = ref(0)
const rssTasks = ref([])
const allQbDownloaders = ref([])
const siteIdentities = ref([])
const mediaState = ref('')
const mediaType = ref('')
const qbDownloaders = ref([])
const qbDownloader = ref('')
const qbView = ref('')
const qbKeyword = ref('')
const qbTask = ref(null)
let qbPollTimer = null

const tabs = [
  { title: '总览', value: 'overview', icon: 'mdi-view-dashboard-outline' },
  { title: '入库管理', value: 'library', icon: 'mdi-database-import-outline' },
  { title: 'QB 管理', value: 'qb', icon: 'mdi-download-box-outline' },
  { title: 'VT+', value: 'vt', icon: 'mdi-rss-box' },
  { title: '后台任务', value: 'tasks', icon: 'mdi-progress-clock' },
]

const mediaHeaders = [
  { title: '标题', key: 'title', minWidth: 190 },
  { title: '状态', key: 'state', width: 120 },
  { title: '类型', key: 'media_type', width: 100 },
  { title: 'TMDB', key: 'tmdb_id', width: 100 },
  { title: '季', key: 'season', width: 70 },
  { title: '分类', key: 'category', width: 120 },
  { title: '更新时间', key: 'updated_at', minWidth: 170 },
]

const torrentHeaders = [
  { title: '识别结果', key: 'media_title', minWidth: 210 },
  { title: '源名称', key: 'name', minWidth: 250 },
  { title: '库存', key: 'inventory_state', width: 110 },
  { title: '识别', key: 'recognition_state', width: 110 },
  { title: '下载状态', key: 'state', width: 120 },
  { title: '进度', key: 'progress', width: 100 },
  { title: '节点', key: 'downloader_id', width: 130 },
  { title: '分类', key: 'category', width: 110 },
  { title: '库存路径', key: 'target_name', minWidth: 280 },
  { title: '硬链接路径', key: 'link_target', minWidth: 280 },
  { title: 'Hash', key: 'info_hash', width: 120 },
]

const rssHistoryHeaders = [
  { title: '标题', key: 'title', minWidth: 220 },
  { title: '任务', key: 'task_id', width: 150 },
  { title: '状态', key: 'status', width: 120 },
  { title: '原因', key: 'reason', minWidth: 220 },
  { title: '时间', key: 'updated_at', minWidth: 170 },
]

const siteHeaders = [
  { title: '站点', key: 'name', minWidth: 180 },
  { title: '地址', key: 'domain', minWidth: 260 },
  { title: '认证方式', key: 'auth_mode', width: 120 },
  { title: '启用', key: 'enabled', width: 90 },
  { title: '状态', key: 'ready', width: 100 },
]

const taskHeaders = [
  { title: '任务类型', key: 'task_type', minWidth: 160 },
  { title: '状态', key: 'state', width: 110 },
  { title: '当前项目', key: 'current_item', minWidth: 180 },
  { title: '进度', key: 'progress_text', width: 120 },
  { title: '更新时间', key: 'updated_at', minWidth: 170 },
]

const capabilityRows = computed(() => Object.entries(
  overview.value.capabilities || {},
).map(([name, value]) => ({
  name,
  ready: Boolean(value?.ready),
  phase: value?.phase || value?.mode || '-',
})))

const qbRefreshing = computed(() => ['queued', 'running'].includes(qbTask.value?.state))
const qbProgress = computed(() => {
  const processed = Number(qbTask.value?.processed || 0)
  const taskTotal = Number(qbTask.value?.total || 0)
  return taskTotal > 0 ? Math.round((processed / taskTotal) * 100) : 0
})

const inventoryLabels = {
  exists: '已存在',
  partial: '不完整',
  missing: '不存在',
  empty: '空资源',
  ambiguous: '目录冲突',
  unconfigured: '未配置',
  unavailable: '不可访问',
  unknown: '未知',
}

const recognitionLabels = {
  identified: '已识别',
  unidentified: '未识别',
  error: '失败',
  pending: '待识别',
}

function unwrap(response) {
  return response?.data ?? response
}

function normalizeTaskRows(items) {
  return (items || []).map(item => ({
    ...item,
    progress_text: `${item.processed || 0}/${item.total || 0}`,
  }))
}

async function loadOverview() {
  const response = unwrap(await props.api.get('plugin/RssAllInOne/overview'))
  overview.value = response || overview.value
  if (response?.qb_task?.id && !qbTask.value?.id) {
    qbTask.value = response.qb_task
    scheduleQbPoll(response.qb_task.id)
  }
}

async function loadQbDownloaders() {
  const response = unwrap(
    await props.api.get('plugin/RssAllInOne/qb/downloaders'),
  )
  allQbDownloaders.value = response?.items || []
  qbDownloaders.value = allQbDownloaders.value
    .filter(item => (item.categories || []).length > 0)
    .map(item => ({
      title: `${item.name}${item.default ? ' · 默认' : ''}${item.ready ? '' : ' · 未就绪'} · ${item.categories?.join(', ') || '无管理分类'}`,
      value: item.name,
      disabled: !item.ready,
    }))
}

async function loadSites(strict = false) {
  const response = unwrap(await props.api.get('plugin/RssAllInOne/sites'))
  if (!response?.success) {
    siteIdentities.value = []
    if (strict) throw new Error(response?.message || '读取站点身份失败')
    return
  }
  siteIdentities.value = response.items || []
}

async function loadActive() {
  loading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await loadOverview()
    if (activeTab.value === 'overview') {
      rows.value = []
      total.value = 0
      return
    }

    if (activeTab.value === 'vt' && vtTab.value === 'rss_tasks') {
      const [response] = await Promise.all([
        props.api.get('plugin/RssAllInOne/rss/tasks', {
          params: { offset: 0, limit: 100 },
        }).then(unwrap),
        loadQbDownloaders(),
        loadSites(false),
      ])
      rssTasks.value = response?.items || []
      rows.value = []
      total.value = Number(response?.total || 0)
      return
    }

    if (activeTab.value === 'vt' && vtTab.value === 'sites') {
      await loadSites(true)
      rows.value = siteIdentities.value
      total.value = siteIdentities.value.length
      return
    }

    let path = ''
    let params = { offset: 0, limit: 100 }
    if (activeTab.value === 'library') {
      path = 'media'
      params = {
        ...params,
        state: mediaState.value,
        media_type: mediaType.value,
      }
    } else if (activeTab.value === 'qb') {
      path = 'torrents'
      params = {
        ...params,
        downloader_id: qbDownloader.value,
        view: qbView.value,
        keyword: qbKeyword.value.trim(),
      }
    } else if (activeTab.value === 'tasks') {
      path = 'tasks'
    } else if (activeTab.value === 'vt' && vtTab.value === 'rss_history') {
      path = 'rss/history'
    }

    if (!path) {
      rows.value = []
      total.value = 0
      return
    }
    const response = unwrap(
      await props.api.get(`plugin/RssAllInOne/${path}`, { params }),
    )
    const items = response?.items || []
    if (activeTab.value === 'tasks') {
      rows.value = normalizeTaskRows(items)
    } else if (activeTab.value === 'qb') {
      rows.value = items.map(item => ({
        ...item,
        row_key: `${item.downloader_id}:${item.info_hash}`,
        target_name: item.details?.path_plan?.inventory_files?.[0]?.path || '',
        link_target: item.details?.path_plan?.link_files?.[0]?.path || '',
      }))
    } else {
      rows.value = items
    }
    total.value = Number(response?.total || 0)
  } catch (error) {
    errorMessage.value = error?.message || '数据加载失败'
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function saveRssTasks(items) {
  loading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/rss/tasks', { items }),
    )
    if (!response?.success) {
      throw new Error(response?.message || 'RSS 任务保存失败')
    }
    rssTasks.value = response.items || []
    total.value = Number(response.total || 0)
    successMessage.value = response.message || 'RSS 任务已保存'
    await Promise.all([loadOverview(), loadQbDownloaders()])
  } catch (error) {
    errorMessage.value = error?.message || 'RSS 任务保存失败'
  } finally {
    loading.value = false
  }
}

function scheduleQbPoll(taskId) {
  if (!taskId) return
  window.clearTimeout(qbPollTimer)
  qbPollTimer = window.setTimeout(() => pollQbTask(taskId), 1200)
}

async function pollQbTask(taskId) {
  try {
    const response = unwrap(
      await props.api.get(`plugin/RssAllInOne/tasks/${taskId}`),
    )
    if (!response?.success || !response?.task) return
    qbTask.value = response.task
    if (['queued', 'running'].includes(response.task.state)) {
      scheduleQbPoll(taskId)
    } else {
      await loadActive()
    }
  } catch (error) {
    errorMessage.value = error?.message || '读取 QB 刷新进度失败'
  }
}

async function refreshQb() {
  errorMessage.value = ''
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/qb/refresh', {
        force_recognition: true,
      }),
    )
    if (!response?.success && !response?.task_id) {
      errorMessage.value = response?.message || 'QB 刷新启动失败'
      return
    }
    qbTask.value = {
      id: response.task_id,
      state: 'running',
      processed: 0,
      total: 0,
      current_item: '',
    }
    scheduleQbPoll(response.task_id)
  } catch (error) {
    errorMessage.value = error?.message || 'QB 刷新启动失败'
  }
}

function inventoryColor(state) {
  return {
    exists: 'success',
    partial: 'warning',
    missing: 'info',
    empty: 'warning',
    ambiguous: 'error',
    unavailable: 'error',
    unconfigured: 'warning',
  }[state] || 'default'
}

function inventoryText(item) {
  const label = inventoryLabels[item.inventory_state] || item.inventory_state
  const inventory = item.details?.inventory || {}
  const totalFiles = Number(inventory.total_files ?? inventory.total ?? 0)
  const existsCount = Number(inventory.exists_count ?? inventory.exists ?? 0)
  if (totalFiles > 0 && ['exists', 'partial', 'missing'].includes(item.inventory_state)) {
    return `${label} ${existsCount}/${totalFiles}`
  }
  return label
}

function recognitionColor(state) {
  return {
    identified: 'success',
    unidentified: 'warning',
    error: 'error',
  }[state] || 'default'
}

watch(activeTab, async value => {
  if (value === 'qb' && qbDownloaders.value.length === 0) {
    try {
      await loadQbDownloaders()
    } catch (error) {
      errorMessage.value = error?.message || '读取 qB 节点失败'
    }
  }
  await loadActive()
})
watch(vtTab, () => {
  if (activeTab.value === 'vt') loadActive()
})
watch([mediaState, mediaType], () => {
  if (activeTab.value === 'library') loadActive()
})
watch([qbDownloader, qbView], () => {
  if (activeTab.value === 'qb') loadActive()
})
onMounted(loadActive)
onBeforeUnmount(() => window.clearTimeout(qbPollTimer))
</script>

<template>
  <div class="app-page">
    <VToolbar density="comfortable" color="surface" class="topbar">
      <VIcon icon="mdi-rss" color="primary" class="ms-3 me-3" />
      <div class="title-block">
        <div class="text-h6">RSS一条龙</div>
        <div class="text-caption text-medium-emphasis">
          {{ overview.plugin?.enabled ? '运行已启用' : '运行未启用' }}
        </div>
      </div>
      <VSpacer />
      <VChip color="info" variant="tonal" size="small" class="me-2">v{{ overview.plugin?.version || '0.4.0' }}</VChip>
      <VTooltip text="刷新">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-refresh"
            variant="text"
            :loading="loading"
            aria-label="刷新"
            @click="loadActive"
          />
        </template>
      </VTooltip>
    </VToolbar>

    <VTabs
      v-model="activeTab"
      color="primary"
      density="compact"
      show-arrows
      class="main-tabs"
    >
      <VTab v-for="tab in tabs" :key="tab.value" :value="tab.value">
        <VIcon :icon="tab.icon" size="18" class="me-2" />
        {{ tab.title }}
      </VTab>
    </VTabs>

    <VAlert v-if="errorMessage" type="error" variant="tonal" class="status-alert">
      {{ errorMessage }}
    </VAlert>
    <VAlert v-if="successMessage" type="success" variant="tonal" class="status-alert">
      {{ successMessage }}
    </VAlert>

    <main class="workspace">
      <section v-if="activeTab === 'overview'" class="overview-section">
        <div class="metric-grid">
          <VSheet border class="metric-item">
            <span class="text-caption text-medium-emphasis">媒体记录</span>
            <strong>{{ overview.counts?.media || 0 }}</strong>
          </VSheet>
          <VSheet border class="metric-item">
            <span class="text-caption text-medium-emphasis">qB 快照</span>
            <strong>{{ overview.counts?.torrents || 0 }}</strong>
          </VSheet>
          <VSheet border class="metric-item">
            <span class="text-caption text-medium-emphasis">RSS 历史</span>
            <strong>{{ overview.counts?.rss_history || 0 }}</strong>
          </VSheet>
          <VSheet border class="metric-item">
            <span class="text-caption text-medium-emphasis">后台任务</span>
            <strong>{{ overview.counts?.background_tasks || 0 }}</strong>
          </VSheet>
        </div>

        <VTable density="compact" class="capability-table">
          <thead>
            <tr>
              <th>能力</th>
              <th>状态</th>
              <th>阶段</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in capabilityRows" :key="item.name">
              <td>{{ item.name }}</td>
              <td>
                <VChip :color="item.ready ? 'success' : 'warning'" size="small" variant="tonal">
                  {{ item.ready ? '就绪' : '待接入' }}
                </VChip>
              </td>
              <td>{{ item.phase }}</td>
            </tr>
          </tbody>
        </VTable>
      </section>

      <section v-else-if="activeTab === 'library'">
        <div class="filter-bar">
          <VSelect
            v-model="mediaState"
            :items="[
              { title: '全部状态', value: '' },
              { title: '已发现', value: 'discovered' },
              { title: '已识别', value: 'identified' },
              { title: '未识别', value: 'unidentified' },
              { title: '已存在', value: 'existing' },
              { title: '待入库', value: 'pending' },
              { title: '入库中', value: 'importing' },
              { title: '已入库', value: 'imported' },
            ]"
            label="状态"
            density="compact"
            hide-details
            class="filter-control"
          />
          <VSelect
            v-model="mediaType"
            :items="[
              { title: '全部类型', value: '' },
              { title: '电影', value: 'movie' },
              { title: '电视剧', value: 'tv' },
            ]"
            label="类型"
            density="compact"
            hide-details
            class="filter-control"
          />
          <span class="text-caption text-medium-emphasis">{{ total }} 项</span>
        </div>
        <VDataTable
          :headers="mediaHeaders"
          :items="rows"
          :loading="loading"
          density="compact"
          item-value="id"
          hide-default-footer
          class="data-table"
          no-data-text="暂无媒体记录"
        />
      </section>

      <section v-else-if="activeTab === 'qb'">
        <div class="qb-toolbar">
          <VSelect
            v-model="qbDownloader"
            :items="[{ title: '全部节点', value: '' }, ...qbDownloaders]"
            label="QB 节点"
            density="compact"
            hide-details
            class="filter-control"
          />
          <VBtnToggle
            v-model="qbView"
            mandatory
            divided
            density="compact"
            variant="outlined"
            color="primary"
          >
            <VBtn value="">全部</VBtn>
            <VBtn value="existing">已存在</VBtn>
            <VBtn value="pending">待下载</VBtn>
          </VBtnToggle>
          <VTextField
            v-model="qbKeyword"
            label="搜索名称或 Hash"
            prepend-inner-icon="mdi-magnify"
            density="compact"
            hide-details
            clearable
            class="qb-search"
            @keyup.enter="loadActive"
            @click:clear="loadActive"
          />
          <VSpacer />
          <span class="text-caption text-medium-emphasis">{{ total }} 项</span>
          <VBtn
            color="primary"
            variant="tonal"
            prepend-icon="mdi-refresh"
            :loading="qbRefreshing"
            :disabled="qbRefreshing || !overview.plugin?.enabled"
            @click="refreshQb"
          >
            刷新识别
          </VBtn>
        </div>
        <VAlert
          v-if="qbTask"
          :type="qbTask.state === 'failed' ? 'error' : 'info'"
          variant="tonal"
          density="compact"
          class="qb-task-status"
        >
          <div class="qb-task-line">
            <span>{{ qbRefreshing ? '正在读取 QB、识别并核对本地库存' : `任务状态：${qbTask.state}` }}</span>
            <span>{{ qbTask.processed || 0 }}/{{ qbTask.total || 0 }}</span>
          </div>
          <VProgressLinear
            v-if="qbRefreshing"
            :model-value="qbProgress"
            height="4"
            class="mt-2"
          />
          <div v-if="qbTask.current_item" class="text-caption mt-1 text-truncate">
            {{ qbTask.current_item }}
          </div>
        </VAlert>
        <VDataTable
          :headers="torrentHeaders"
          :items="rows"
          :loading="loading"
          density="compact"
          item-value="row_key"
          hide-default-footer
          class="data-table"
          no-data-text="暂无 qB 任务快照"
        >
          <template #item.media_title="{ item }">
            <div class="media-cell">
              <strong>{{ item.media_title || '未识别' }}</strong>
              <span v-if="item.media_year || item.season !== null" class="text-caption text-medium-emphasis">
                {{ item.media_year || '' }}{{ item.season !== null && item.season !== undefined ? ` · S${String(item.season).padStart(2, '0')}` : '' }}
              </span>
            </div>
          </template>
          <template #item.inventory_state="{ item }">
            <VChip :color="inventoryColor(item.inventory_state)" size="small" variant="tonal">
              {{ inventoryText(item) }}
            </VChip>
          </template>
          <template #item.recognition_state="{ item }">
            <VChip :color="recognitionColor(item.recognition_state)" size="small" variant="tonal">
              {{ recognitionLabels[item.recognition_state] || item.recognition_state }}
            </VChip>
          </template>
          <template #item.progress="{ item }">
            <div class="progress-cell">
              <VProgressLinear :model-value="Number(item.progress || 0)" height="5" />
              <span>{{ Math.round(Number(item.progress || 0)) }}%</span>
            </div>
          </template>
          <template #item.info_hash="{ item }">
            <code>{{ String(item.info_hash || '').slice(0, 10) }}</code>
          </template>
        </VDataTable>
      </section>

      <section v-else-if="activeTab === 'vt'">
        <VTabs v-model="vtTab" density="compact" color="primary" class="sub-tabs">
          <VTab value="rss_tasks">RSS任务</VTab>
          <VTab value="rss_history">RSS历史</VTab>
          <VTab value="sites">站点访问身份</VTab>
        </VTabs>
        <RssTaskEditor
          v-if="vtTab === 'rss_tasks'"
          :items="rssTasks"
          :downloaders="allQbDownloaders"
          :sites="siteIdentities"
          :loading="loading"
          @save="saveRssTasks"
          @reload="loadActive"
        />
        <VDataTable
          v-else-if="vtTab === 'rss_history'"
          :headers="rssHistoryHeaders"
          :items="rows"
          :loading="loading"
          density="compact"
          item-value="id"
          hide-default-footer
          class="data-table"
          no-data-text="暂无 RSS 历史"
        />
        <VDataTable
          v-else
          :headers="siteHeaders"
          :items="siteIdentities"
          :loading="loading"
          density="compact"
          item-value="id"
          hide-default-footer
          class="data-table"
          no-data-text="暂无可用站点身份"
        >
          <template #item.enabled="{ item }">
            <VChip :color="item.enabled ? 'success' : 'default'" size="small" variant="tonal">
              {{ item.enabled ? '已启用' : '未启用' }}
            </VChip>
          </template>
          <template #item.ready="{ item }">
            <VChip :color="item.ready ? 'success' : 'warning'" size="small" variant="tonal">
              {{ item.ready ? '可用' : '未就绪' }}
            </VChip>
          </template>
        </VDataTable>
      </section>

      <section v-else-if="activeTab === 'tasks'">
        <div class="section-count">{{ total }} 个后台任务</div>
        <VDataTable
          :headers="taskHeaders"
          :items="rows"
          :loading="loading"
          density="compact"
          item-value="id"
          hide-default-footer
          class="data-table"
          no-data-text="暂无后台任务"
        />
      </section>
    </main>
  </div>
</template>

<style scoped>
.app-page {
  min-height: 100%;
  min-width: 0;
  background: rgb(var(--v-theme-background));
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 12;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.title-block {
  min-width: 0;
  line-height: 1.2;
}

.main-tabs,
.sub-tabs {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
}

.status-alert {
  margin: 12px 16px 0;
}

.workspace {
  width: 100%;
  padding: 16px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.metric-item {
  display: flex;
  min-height: 78px;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 6px;
}

.metric-item strong {
  font-size: 1.45rem;
  font-weight: 600;
}

.capability-table,
.data-table {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 6px;
  overflow: hidden;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.qb-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.qb-search {
  flex: 1 1 240px;
  min-width: 200px;
  max-width: 380px;
}

.qb-task-status {
  margin-bottom: 12px;
}

.qb-task-line,
.progress-cell,
.media-cell {
  display: flex;
  min-width: 0;
}

.qb-task-line {
  justify-content: space-between;
  gap: 12px;
}

.progress-cell {
  min-width: 80px;
  align-items: center;
  gap: 8px;
}

.progress-cell .v-progress-linear {
  min-width: 48px;
}

.media-cell {
  flex-direction: column;
  line-height: 1.35;
}

.media-cell strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.filter-control {
  flex: 0 1 190px;
  min-width: 150px;
}

.section-count {
  margin-bottom: 10px;
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 0.8rem;
}

.sub-tabs {
  margin: -16px -16px 14px;
  padding-inline: 8px;
}

@media (max-width: 760px) {
  .workspace {
    padding: 10px;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .sub-tabs {
    margin: -10px -10px 10px;
  }

  .filter-control {
    flex: 1 1 160px;
  }
}
</style>
