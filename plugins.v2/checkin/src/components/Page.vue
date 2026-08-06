<script setup>
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  api: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['switch', 'close'])
const loading = ref(false)
const running = ref('')
const rows = ref([])
const snackbar = ref({ show: false, text: '', color: 'success' })

const headers = [
  { title: '站点', key: 'site_name', width: 140 },
  { title: '状态', key: 'status_label', width: 120 },
  { title: '说明', key: 'message', minWidth: 260 },
  { title: '账号', key: 'username', width: 130 },
  { title: '连续签到', key: 'days', width: 110 },
  { title: '积分', key: 'points', width: 130 },
  { title: '触发', key: 'trigger_label', width: 90 },
  { title: '时间', key: 'date', width: 180 },
]

const summary = computed(() => {
  const latest = {}
  for (const row of rows.value) {
    if (!latest[row.site]) latest[row.site] = row
  }
  return latest
})

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

function displayRow(record) {
  const statusLabels = {
    success: '成功',
    already: '今日已完成',
    failed: '失败',
    busy: '执行中',
  }
  return {
    ...record,
    status_label: statusLabels[record.status] || record.status || '-',
    trigger_label: record.trigger === 'scheduled' ? '定时' : '手动',
  }
}

function statusColor(status) {
  if (status === 'success') return 'success'
  if (status === 'already') return 'info'
  if (status === 'busy') return 'warning'
  return 'error'
}

async function loadHistory() {
  loading.value = true
  try {
    const response = unwrap(await props.api.get('plugin/Checkin/history'))
    rows.value = (response?.items || []).map(displayRow)
  } catch (error) {
    notify(error?.message || '签到历史加载失败', 'error')
  } finally {
    loading.value = false
  }
}

async function run(site) {
  running.value = site
  try {
    const response = unwrap(await props.api.post('plugin/Checkin/run', { site }))
    notify(
      response?.message || '签到执行完成',
      response?.success === false ? 'error' : 'success',
    )
    await loadHistory()
  } catch (error) {
    notify(error?.message || '签到执行失败', 'error')
  } finally {
    running.value = ''
  }
}

async function clearHistory() {
  try {
    const response = unwrap(await props.api.post('plugin/Checkin/history/clear'))
    notify(response?.message || '签到历史已清空')
    await loadHistory()
  } catch (error) {
    notify(error?.message || '清空失败', 'error')
  }
}

onMounted(loadHistory)
</script>

<template>
  <div class="page-root">
    <VToolbar density="comfortable" color="transparent">
      <div class="text-h6 ms-3">签到助手</div>
      <VSpacer />
      <VTooltip text="刷新">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-refresh"
            variant="text"
            :loading="loading"
            @click="loadHistory"
          />
        </template>
      </VTooltip>
      <VTooltip text="设置">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-cog-outline"
            variant="text"
            @click="emit('switch')"
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

    <div class="actions-band">
      <div class="site-action">
        <div>
          <div class="site-name">什么值得买</div>
          <div class="site-status">
            {{ summary.smzdm?.message || '尚无执行记录' }}
          </div>
        </div>
        <VBtn
          prepend-icon="mdi-calendar-check-outline"
          color="primary"
          variant="tonal"
          :loading="running === 'smzdm'"
          :disabled="Boolean(running)"
          @click="run('smzdm')"
        >
          立即签到
        </VBtn>
      </div>
      <VDivider vertical class="action-divider" />
      <div class="site-action">
        <div>
          <div class="site-name">Chiphell</div>
          <div class="site-status">
            {{ summary.chiphell?.message || '尚无执行记录' }}
          </div>
        </div>
        <VBtn
          prepend-icon="mdi-web-check"
          color="secondary"
          variant="tonal"
          :loading="running === 'chiphell'"
          :disabled="Boolean(running)"
          @click="run('chiphell')"
        >
          立即保活
        </VBtn>
      </div>
    </div>

    <div class="history-toolbar">
      <div class="text-subtitle-1 font-weight-medium">执行历史</div>
      <VSpacer />
      <VTooltip text="清空历史">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-delete-sweep-outline"
            variant="text"
            size="small"
            @click="clearHistory"
          />
        </template>
      </VTooltip>
    </div>
    <VDataTable
      :headers="headers"
      :items="rows"
      :loading="loading"
      :items-per-page="25"
      density="comfortable"
      class="history-table"
    >
      <template #item.status_label="{ item }">
        <VChip :color="statusColor(item.status)" size="small" variant="tonal">
          {{ item.status_label }}
        </VChip>
      </template>
      <template #item.days="{ item }">
        {{ item.days ? `${item.days} 天` : '-' }}
      </template>
      <template #item.username="{ item }">{{ item.username || '-' }}</template>
      <template #item.points="{ item }">{{ item.points || '-' }}</template>
      <template #no-data>
        <div class="empty-state">暂无签到记录</div>
      </template>
    </VDataTable>

    <VSnackbar v-model="snackbar.show" :color="snackbar.color" timeout="3500">
      {{ snackbar.text }}
    </VSnackbar>
  </div>
</template>

<style scoped>
.page-root { min-width: 0; }
.actions-band {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 1px minmax(0, 1fr);
  gap: 20px;
  padding: 20px;
  background: rgba(var(--v-theme-surface-variant), 0.25);
}
.site-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-width: 0;
}
.site-name { font-size: 16px; font-weight: 600; }
.site-status {
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.64);
  overflow-wrap: anywhere;
}
.action-divider { height: 100%; }
.history-toolbar { display: flex; align-items: center; padding: 12px 16px 4px; }
.history-table { width: 100%; }
.empty-state { padding: 40px 16px; color: rgba(var(--v-theme-on-surface), 0.6); }
@media (max-width: 720px) {
  .actions-band { grid-template-columns: 1fr; }
  .action-divider { display: none; }
  .site-action { align-items: flex-start; flex-direction: column; }
  .site-action :deep(.v-btn) { width: 100%; }
}
</style>
