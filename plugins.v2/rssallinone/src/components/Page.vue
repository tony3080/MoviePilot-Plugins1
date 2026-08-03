<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
  api: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['switch', 'close'])
const loading = ref(false)
const overview = ref({ plugin: {}, counts: {}, capabilities: {} })
const errorMessage = ref('')

function unwrap(response) {
  return response?.data ?? response
}

async function loadOverview() {
  loading.value = true
  errorMessage.value = ''
  try {
    overview.value = unwrap(
      await props.api.get('plugin/RssAllInOne/overview'),
    ) || overview.value
  } catch (error) {
    errorMessage.value = error?.message || '状态加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<template>
  <div class="page-root">
    <VToolbar density="comfortable" color="transparent">
      <VIcon icon="mdi-rss" color="primary" class="ms-3 me-3" />
      <div>
        <div class="text-h6">RSS一条龙</div>
        <div class="text-caption text-medium-emphasis">v{{ overview.plugin?.version || '0.4.0' }}</div>
      </div>
      <VSpacer />
      <VTooltip text="刷新状态">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-refresh"
            variant="text"
            :loading="loading"
            aria-label="刷新状态"
            @click="loadOverview"
          />
        </template>
      </VTooltip>
      <VTooltip text="插件设置">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-cog-outline"
            variant="text"
            aria-label="插件设置"
            @click="emit('switch')"
          />
        </template>
      </VTooltip>
    </VToolbar>
    <VDivider />

    <VAlert v-if="errorMessage" type="error" variant="tonal" class="ma-4">
      {{ errorMessage }}
    </VAlert>

    <div class="summary-grid">
      <VSheet border class="summary-item">
        <div class="text-caption text-medium-emphasis">媒体记录</div>
        <div class="text-h5">{{ overview.counts?.media || 0 }}</div>
      </VSheet>
      <VSheet border class="summary-item">
        <div class="text-caption text-medium-emphasis">qB 快照</div>
        <div class="text-h5">{{ overview.counts?.torrents || 0 }}</div>
      </VSheet>
      <VSheet border class="summary-item">
        <div class="text-caption text-medium-emphasis">RSS 任务</div>
        <div class="text-h5">{{ overview.counts?.rss_tasks || 0 }}</div>
      </VSheet>
      <VSheet border class="summary-item">
        <div class="text-caption text-medium-emphasis">CD2 监控</div>
        <div class="text-h5">{{ overview.counts?.import_watches || 0 }}</div>
      </VSheet>
    </div>

    <div class="status-row">
      <VChip
        :color="overview.plugin?.enabled ? 'success' : 'default'"
        variant="tonal"
        size="small"
      >
        {{ overview.plugin?.enabled ? '已启用' : '未启用' }}
      </VChip>
      <VChip
        :color="overview.capabilities?.clouddrive?.ready ? 'success' : 'warning'"
        variant="tonal"
        size="small"
      >
        CloudDrive2 {{ overview.capabilities?.clouddrive?.ready ? '依赖就绪' : '待配置' }}
      </VChip>
      <VChip
        :color="overview.capabilities?.local_inventory?.ready ? 'success' : 'warning'"
        variant="tonal"
        size="small"
      >
        本地库存 {{ overview.capabilities?.local_inventory?.ready ? '可访问' : '待配置' }}
      </VChip>
      <VChip color="info" variant="tonal" size="small">QB 只读阶段</VChip>
    </div>
  </div>
</template>

<style scoped>
.page-root {
  min-width: 0;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  padding: 16px;
}

.summary-item {
  min-height: 82px;
  padding: 14px;
  border-radius: 6px;
}

.status-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 16px 16px;
}

@media (max-width: 720px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
