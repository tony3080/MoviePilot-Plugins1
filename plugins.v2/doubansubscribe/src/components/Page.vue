<script setup>
import { computed, onMounted, ref, watch } from 'vue'

const props = defineProps({
  api: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['close'])

const activeTab = ref('history')
const loading = ref(false)
const running = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(25)
const keywordInput = ref('')
const keyword = ref('')
const group = ref('all')
const category = ref('')
const retrying = ref(new Set())
const managed = ref([])
const supplement = ref({})
const lastRun = ref({})
const snackbar = ref({ show: false, text: '', color: 'success' })
const diagnostics = ref({ show: false, title: '', attempts: [] })

const groups = [
  { title: '全部', value: 'all' },
  { title: '失败', value: 'failure' },
  { title: '成功', value: 'success' },
  { title: '跳过', value: 'skipped' },
]

const categories = [
  { title: '全部地区', value: '' },
  { title: '国产剧', value: 'domestic' },
  { title: '欧美剧', value: 'western' },
  { title: '日韩剧', value: 'japan_korea' },
  { title: '其他地区', value: 'other' },
]

const historyHeaders = [
  { title: '标题', key: 'title', minWidth: 180 },
  { title: '状态', key: 'status', width: 150 },
  { title: '地区', key: 'category', width: 100 },
  { title: '豆瓣总集数', key: 'douban_total', width: 112 },
  { title: 'TMDB / 季', key: 'tmdb', width: 130 },
  { title: '时间', key: 'time', minWidth: 190 },
  { title: '原因', key: 'reason', minWidth: 260 },
  { title: '', key: 'actions', sortable: false, width: 96, align: 'end' },
]

const managedHeaders = [
  { title: '订阅', key: 'title', minWidth: 200 },
  { title: '季度', key: 'season', width: 80 },
  { title: '目标总集数', key: 'expected_total', width: 112 },
  { title: '状态', key: 'status', width: 180 },
  { title: '下次检查', key: 'check_after', minWidth: 190 },
  { title: '说明', key: 'reason', minWidth: 260 },
]

const supplementHeaders = [
  { title: '订阅', key: 'title', minWidth: 200 },
  { title: '早间进度', key: 'start_progress', width: 110 },
  { title: '当前进度', key: 'current_progress', width: 110 },
  { title: '状态', key: 'status', width: 150 },
  { title: '搜索时间', key: 'searched_at', minWidth: 190 },
]

const supplementItems = computed(() => supplement.value?.items || [])

function unwrap(response) {
  if (
    response
    && Object.prototype.hasOwnProperty.call(response, 'data')
    && response.success !== undefined
  ) {
    return response.data
  }
  return response?.data ?? response
}

function notify(text, color = 'success') {
  snackbar.value = { show: true, text, color }
}

function statusColor(status) {
  if (['subscribed', 'existing', 'history_existing'].includes(status)) return 'success'
  if (status === 'category_skipped') return 'warning'
  return 'error'
}

function categoryLabel(value) {
  return categories.find(item => item.value === value)?.title || value || '-'
}

function displayRow(record) {
  return {
    ...record,
    tmdb: record.tmdb_id
      ? `${record.tmdb_id} / S${String(record.season || 1).padStart(2, '0')}`
      : '',
  }
}

async function loadOverview() {
  try {
    const response = unwrap(await props.api.get('plugin/DoubanSubscribe/history'))
    managed.value = response?.managed || []
    supplement.value = response?.supplement || {}
    lastRun.value = response?.last_run || {}
  } catch (error) {
    notify(error?.message || '状态加载失败', 'error')
  }
}

async function loadHistory() {
  loading.value = true
  try {
    const params = {
      keyword: keyword.value,
      group: group.value === 'all' ? '' : group.value,
      category: category.value,
      offset: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
    }
    const response = unwrap(
      await props.api.get('plugin/DoubanSubscribe/history/search', { params }),
    )
    rows.value = (response?.items || []).map(displayRow)
    total.value = Number(response?.total || 0)
  } catch (error) {
    notify(error?.message || 'RSS 处理记录加载失败', 'error')
  } finally {
    loading.value = false
  }
}

function search() {
  keyword.value = keywordInput.value.trim()
  page.value = 1
  loadHistory()
}

function clearSearch() {
  keywordInput.value = ''
  keyword.value = ''
  page.value = 1
  loadHistory()
}

async function runNow() {
  running.value = true
  try {
    const response = unwrap(await props.api.post('plugin/DoubanSubscribe/run'))
    notify(response?.message || 'RSS 处理已启动', response?.success === false ? 'error' : 'success')
  } catch (error) {
    notify(error?.message || '启动失败', 'error')
  } finally {
    running.value = false
  }
}

async function retry(record) {
  const next = new Set(retrying.value)
  next.add(record.key)
  retrying.value = next
  try {
    const response = unwrap(
      await props.api.post('plugin/DoubanSubscribe/history/retry', { key: record.key }),
    )
    notify(response?.message || '重试完成', response?.success === false ? 'error' : 'success')
    await Promise.all([loadHistory(), loadOverview()])
  } catch (error) {
    notify(error?.message || '重试失败', 'error')
  } finally {
    const done = new Set(retrying.value)
    done.delete(record.key)
    retrying.value = done
  }
}

function showDiagnostics(record) {
  diagnostics.value = {
    show: true,
    title: record.title || 'TMDB 查询诊断',
    attempts: record.search_attempts || [],
  }
}

watch([group, category], () => {
  if (page.value !== 1) {
    page.value = 1
  } else {
    loadHistory()
  }
})

watch([page, pageSize], () => {
  loadHistory()
})

onMounted(() => {
  loadHistory()
  loadOverview()
})
</script>

<template>
  <div class="page-root">
    <VToolbar density="comfortable" class="page-toolbar">
      <div class="text-h6 ms-3">豆瓣订阅助手</div>
      <VSpacer />
      <VTooltip text="立即处理 RSS">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-play"
            variant="text"
            :loading="running"
            @click="runNow"
          />
        </template>
      </VTooltip>
      <VTooltip text="刷新">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-refresh"
            variant="text"
            :loading="loading"
            @click="Promise.all([loadHistory(), loadOverview()])"
          />
        </template>
      </VTooltip>
      <VTooltip text="关闭">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-close"
            variant="text"
            @click="emit('close')"
          />
        </template>
      </VTooltip>
    </VToolbar>
    <VDivider />

    <VTabs v-model="activeTab" density="comfortable">
      <VTab value="history">RSS 处理记录</VTab>
      <VTab value="managed">受管订阅</VTab>
      <VTab value="supplement">今日补齐</VTab>
    </VTabs>
    <VDivider />

    <VWindow v-model="activeTab">
      <VWindowItem value="history">
        <div class="history-tools">
          <div class="search-row">
            <VTextField
              v-model="keywordInput"
              label="搜索处理记录"
              prepend-inner-icon="mdi-magnify"
              density="compact"
              hide-details
              clearable
              @keyup.enter="search"
              @click:clear="clearSearch"
            />
            <VTooltip text="搜索">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  icon="mdi-magnify"
                  color="primary"
                  variant="tonal"
                  @click="search"
                />
              </template>
            </VTooltip>
            <VTooltip text="清除">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  icon="mdi-filter-remove-outline"
                  variant="text"
                  @click="clearSearch"
                />
              </template>
            </VTooltip>
          </div>
          <div class="filter-row">
            <VBtnToggle
              v-model="group"
              mandatory
              density="compact"
              color="primary"
              divided
            >
              <VBtn v-for="item in groups" :key="item.value" :value="item.value">
                {{ item.title }}
              </VBtn>
            </VBtnToggle>
            <VSelect
              v-model="category"
              :items="categories"
              label="地区"
              density="compact"
              hide-details
              class="category-select"
            />
            <div class="text-body-2 text-medium-emphasis result-count">
              共 {{ total }} 条
            </div>
          </div>
        </div>

        <VDataTableServer
          v-model:page="page"
          v-model:items-per-page="pageSize"
          :headers="historyHeaders"
          :items="rows"
          :items-length="total"
          :loading="loading"
          :items-per-page-options="[10, 25, 50, 100]"
          item-value="key"
          fixed-header
          class="history-table"
        >
          <template #item.title="{ item }">
            <div class="title-cell">
              <div>{{ item.douban_title || item.title }}</div>
              <div v-if="item.douban_id" class="text-caption text-medium-emphasis">
                豆瓣 {{ item.douban_id }}
              </div>
            </div>
          </template>
          <template #item.status="{ item }">
            <VChip :color="statusColor(item.status)" size="small" variant="tonal">
              {{ item.status }}
            </VChip>
          </template>
          <template #item.category="{ item }">
            {{ categoryLabel(item.category) }}
          </template>
          <template #item.actions="{ item }">
            <div class="row-actions">
              <VTooltip v-if="item.search_attempts?.length" text="TMDB 查询诊断">
                <template #activator="{ props: tooltipProps }">
                  <VBtn
                    v-bind="tooltipProps"
                    icon="mdi-text-search"
                    size="small"
                    variant="text"
                    @click="showDiagnostics(item)"
                  />
                </template>
              </VTooltip>
              <VTooltip v-if="item.retryable" text="重试">
                <template #activator="{ props: tooltipProps }">
                  <VBtn
                    v-bind="tooltipProps"
                    icon="mdi-refresh"
                    size="small"
                    variant="text"
                    color="primary"
                    :loading="retrying.has(item.key)"
                    @click="retry(item)"
                  />
                </template>
              </VTooltip>
            </div>
          </template>
        </VDataTableServer>
      </VWindowItem>

      <VWindowItem value="managed">
        <VDataTable
          :headers="managedHeaders"
          :items="managed"
          :items-per-page="25"
          fixed-header
        />
      </VWindowItem>

      <VWindowItem value="supplement">
        <VAlert
          v-if="supplement.date"
          type="info"
          variant="tonal"
          density="compact"
          class="supplement-status"
        >
          {{ supplement.date }} · {{ supplement.status || '已建立快照' }}
        </VAlert>
        <VDataTable
          :headers="supplementHeaders"
          :items="supplementItems"
          :items-per-page="25"
          fixed-header
        />
      </VWindowItem>
    </VWindow>

    <VDialog v-model="diagnostics.show" max-width="860">
      <VCard>
        <VToolbar density="compact" color="transparent">
          <div class="text-subtitle-1 ms-4 diagnostics-title">
            {{ diagnostics.title }}
          </div>
          <VSpacer />
          <VBtn icon="mdi-close" variant="text" @click="diagnostics.show = false" />
        </VToolbar>
        <VDivider />
        <VTable density="compact" class="diagnostics-table">
          <thead>
            <tr>
              <th>查询词</th>
              <th>模式</th>
              <th>结果</th>
              <th>详情</th>
              <th>请求</th>
              <th>错误</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(attempt, index) in diagnostics.attempts" :key="index">
              <td>{{ attempt.query }}</td>
              <td>{{ attempt.mode }}</td>
              <td>{{ attempt.result_count }}</td>
              <td>{{ attempt.hydrated_count }}</td>
              <td>{{ attempt.request_count }}</td>
              <td class="error-cell">{{ attempt.error || '-' }}</td>
            </tr>
          </tbody>
        </VTable>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">
      {{ snackbar.text }}
    </VSnackbar>
  </div>
</template>

<style scoped>
.page-root {
  min-width: 0;
}

.page-toolbar {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgb(var(--v-theme-surface));
}

.history-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
}

.search-row,
.filter-row,
.row-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-row {
  flex: 1 1 420px;
  max-width: 680px;
}

.filter-row {
  flex: 1 1 auto;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.category-select {
  width: 150px;
  flex: 0 0 150px;
}

.result-count {
  min-width: 76px;
  text-align: right;
}

.history-table {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.title-cell {
  min-width: 0;
  padding-block: 6px;
}

.row-actions {
  justify-content: flex-end;
  min-width: 80px;
}

.supplement-status {
  margin: 12px 16px 0;
}

.diagnostics-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diagnostics-table {
  overflow-x: auto;
}

.error-cell {
  min-width: 180px;
  white-space: normal;
  overflow-wrap: anywhere;
}

@media (max-width: 720px) {
  .history-tools {
    align-items: stretch;
    padding: 12px;
  }

  .search-row,
  .filter-row {
    width: 100%;
  }

  .filter-row {
    justify-content: flex-start;
  }

  .category-select {
    flex: 1 1 140px;
  }

  .result-count {
    margin-left: auto;
  }
}
</style>
