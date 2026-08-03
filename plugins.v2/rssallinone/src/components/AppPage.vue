<script setup>
import { computed, onMounted, ref, watch } from 'vue'

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
const overview = ref({ plugin: {}, counts: {}, capabilities: {} })
const rows = ref([])
const total = ref(0)
const mediaState = ref('')
const mediaType = ref('')

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
  { title: '名称', key: 'name', minWidth: 220 },
  { title: '下载器', key: 'downloader_id', width: 130 },
  { title: 'Hash', key: 'info_hash', minWidth: 180 },
  { title: '状态', key: 'state', width: 120 },
  { title: '分类', key: 'category', width: 120 },
  { title: '进度', key: 'progress', width: 90 },
  { title: '更新时间', key: 'updated_at', minWidth: 170 },
]

const rssTaskHeaders = [
  { title: '任务', key: 'name', minWidth: 200 },
  { title: '启用', key: 'enabled', width: 80 },
  { title: '顺序', key: 'position', width: 80 },
  { title: '更新时间', key: 'updated_at', minWidth: 170 },
]

const rssHistoryHeaders = [
  { title: '标题', key: 'title', minWidth: 220 },
  { title: '任务', key: 'task_id', width: 150 },
  { title: '状态', key: 'status', width: 120 },
  { title: '原因', key: 'reason', minWidth: 220 },
  { title: '时间', key: 'updated_at', minWidth: 170 },
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
}

async function loadActive() {
  loading.value = true
  errorMessage.value = ''
  try {
    await loadOverview()
    if (activeTab.value === 'overview') {
      rows.value = []
      total.value = 0
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
    } else if (activeTab.value === 'tasks') {
      path = 'tasks'
    } else if (activeTab.value === 'vt' && vtTab.value === 'rss_tasks') {
      path = 'rss/tasks'
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
    rows.value = activeTab.value === 'tasks'
      ? normalizeTaskRows(response?.items)
      : (response?.items || [])
    total.value = Number(response?.total || 0)
  } catch (error) {
    errorMessage.value = error?.message || '数据加载失败'
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

watch(activeTab, loadActive)
watch(vtTab, () => {
  if (activeTab.value === 'vt') loadActive()
})
watch([mediaState, mediaType], () => {
  if (activeTab.value === 'library') loadActive()
})
onMounted(loadActive)
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
      <VChip color="info" variant="tonal" size="small" class="me-2">v{{ overview.plugin?.version || '0.1.0' }}</VChip>
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
        <div class="section-count">{{ total }} 个 qB 任务快照</div>
        <VDataTable
          :headers="torrentHeaders"
          :items="rows"
          :loading="loading"
          density="compact"
          item-value="info_hash"
          hide-default-footer
          class="data-table"
          no-data-text="暂无 qB 任务快照"
        />
      </section>

      <section v-else-if="activeTab === 'vt'">
        <VTabs v-model="vtTab" density="compact" color="primary" class="sub-tabs">
          <VTab value="rss_tasks">RSS任务</VTab>
          <VTab value="rss_history">RSS历史</VTab>
          <VTab value="sites">站点身份</VTab>
        </VTabs>
        <VDataTable
          v-if="vtTab === 'rss_tasks'"
          :headers="rssTaskHeaders"
          :items="rows"
          :loading="loading"
          density="compact"
          item-value="id"
          hide-default-footer
          class="data-table"
          no-data-text="暂无 RSS 任务"
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
        <VTable v-else density="compact" class="capability-table">
          <thead>
            <tr><th>来源</th><th>模式</th><th>状态</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>当前 MoviePilot</td>
              <td>站点服务</td>
              <td><VChip size="small" variant="tonal" color="warning">适配器待接入</VChip></td>
            </tr>
          </tbody>
        </VTable>
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
