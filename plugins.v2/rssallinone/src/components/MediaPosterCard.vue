<script setup>
import { computed } from 'vue'

const props = defineProps({
  item: { type: Object, required: true },
  mode: { type: String, default: 'qb' },
  selected: Boolean,
  busy: Boolean,
})

const emit = defineEmits(['toggle', 'refresh', 'edit', 'delete'])

const details = computed(() => props.item.details || {})
const inventory = computed(() => details.value.inventory || {})
const media = computed(() => details.value.media || {})
const override = computed(() => details.value.manual_override || {})
const title = computed(() => props.item.media_title || props.item.title || props.item.source_name || props.item.name || '未识别')
const sourceName = computed(() => props.item.source_name || props.item.name || '')
const poster = computed(() => props.item.poster || media.value.poster_path || media.value.poster || '')
const sourceUrl = computed(() => {
  const value = props.item.comment_url
    || props.item.source_url_masked
    || details.value.rss_source?.detail_url_masked
    || details.value.comment_url
    || details.value.source_url
    || ''
  return usableSourceUrl(value)
})
const mediaType = computed(() => props.item.media_type || override.value.media_type || '')
const tmdbUrl = computed(() => {
  const tmdbId = Number(props.item.tmdb_id || override.value.tmdb_id || 0)
  if (!tmdbId) return ''
  return `https://www.themoviedb.org/${mediaType.value === 'movie' ? 'movie' : 'tv'}/${tmdbId}`
})
const totalFiles = computed(() => Number(inventory.value.total_files ?? inventory.value.total ?? 0))
const existsCount = computed(() => Number(inventory.value.exists_count ?? inventory.value.exists ?? 0))
const customization = computed(() => {
  const expected = details.value.inventory_plan?.expected_files || []
  return [...new Set(expected.map(file => file.recognition?.customization).filter(Boolean))].join('@')
})
const customizationLabel = computed(() => customization.value.replaceAll('@', '@\u200b'))
const resourceTokens = computed(() => {
  const expected = details.value.inventory_plan?.expected_files || []
  return [...new Set(expected.flatMap(file => file.recognition?.resource_tokens || []).filter(Boolean))]
})
const resolution = computed(() => resourceTokens.value.find(value => /^\d{3,4}p$/i.test(value)) || '')
const mediaCategory = computed(() => props.item.media_category || details.value.path_plan?.category || props.item.category || '')
const plannedName = computed(() => details.value.inventory_plan?.expected_directory || props.item.target_name || '')
const sizeText = computed(() => formatSize(Number(props.item.size || details.value.torrent?.size || 0)))
const isImported = computed(() => props.mode === 'imported')
const showDelete = computed(() => props.mode === 'pending')
const showEdit = computed(() => !isImported.value)
const isRolledBack = computed(() => Boolean(props.item.rolled_back) || props.item.state === 'rolled_back')
const hasFailureMarker = computed(() => !isRolledBack.value && Boolean(
  props.item.failure_message || props.item.recognition_error,
))
const status = computed(() => {
  if (props.mode === 'qb') {
    if (props.item.recognition_state === 'unidentified') return { text: '未识别', color: 'error' }
    if (props.item.inventory_state === 'exists') return { text: '已存在', color: 'success' }
    if (details.value.import_control?.import_enabled === false) return { text: '仅下载', color: 'orange' }
    return { text: '待入库', color: 'info' }
  }
  const state = props.item.state || ''
  return {
    recognized: { text: '已识别', color: 'info' },
    identified: { text: '已识别', color: 'info' },
    existing: { text: '已存在', color: 'success' },
    imported: { text: '已入库', color: 'success' },
    rolled_back: { text: '已识别', color: 'info' },
    unidentified: { text: '未识别', color: 'error' },
    pending: { text: '待入库', color: 'purple' },
    pending_import: { text: '待入库', color: 'purple' },
  }[state] || { text: '待入库', color: 'info' }
})
const inventoryText = computed(() => {
  const folderStatus = inventory.value.folder_status || inventory.value.folder?.status || ''
  if (folderStatus === 'ambiguous' || props.item.inventory_state === 'ambiguous') return '目录冲突'
  if (folderStatus === 'exists' || ['exists', 'partial'].includes(props.item.inventory_state)) {
    return `目录已存在（${existsCount.value}/${totalFiles.value}）`
  }
  return `目录未建立${totalFiles.value ? `（0/${totalFiles.value}）` : ''}`
})
const inventoryClass = computed(() => {
  if (inventoryText.value === '目录冲突') return 'inventory-warning'
  return inventoryText.value.startsWith('目录已存在') ? 'inventory-ok' : 'inventory-missing'
})

function formatSize(bytes) {
  if (!bytes) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(unit >= 3 ? 2 : 1)} ${units[unit]}`
}

function openLink(url) {
  if (url) window.open(url, '_blank', 'noopener,noreferrer')
}

function usableSourceUrl(value) {
  const text = String(value || '').trim()
  if (!/^https?:\/\//i.test(text)) return ''
  try {
    const url = new URL(text)
    url.username = ''
    url.password = ''
    for (const [key, itemValue] of [...url.searchParams.entries()]) {
      if (itemValue.includes('***')) url.searchParams.delete(key)
    }
    return url.toString()
  } catch {
    return ''
  }
}
</script>

<template>
  <VCard
    class="media-poster-card"
    :class="{ selected }"
    elevation="0"
    @click="emit('toggle', item)"
  >
    <div class="poster-area">
      <VImg v-if="poster" :src="poster" cover class="poster-image">
        <template #error>
          <div class="poster-placeholder"><VIcon icon="mdi-broken-image" size="42" /></div>
        </template>
      </VImg>
      <div v-else class="poster-placeholder">
        <VIcon :icon="item.recognition_state === 'unidentified' ? 'mdi-broken-image' : 'mdi-movie-open-outline'" size="42" />
      </div>

      <div class="poster-left-actions" @click.stop>
        <VTooltip v-if="isRolledBack" text="已回退">
          <template #activator="{ props: tooltipProps }">
            <span v-bind="tooltipProps" class="corner-badge rollback">R</span>
          </template>
        </VTooltip>
        <VTooltip v-if="hasFailureMarker" :text="item.failure_message || item.recognition_error || '入库失败'">
          <template #activator="{ props: tooltipProps }">
            <span v-bind="tooltipProps" class="corner-badge failure">!</span>
          </template>
        </VTooltip>
        <VTooltip v-if="sourceUrl" text="打开来源页面">
          <template #activator="{ props: tooltipProps }">
            <button v-bind="tooltipProps" type="button" class="corner-badge source" @click="openLink(sourceUrl)">P</button>
          </template>
        </VTooltip>
        <VTooltip v-if="tmdbUrl" text="打开 TMDB">
          <template #activator="{ props: tooltipProps }">
            <button v-bind="tooltipProps" type="button" class="corner-badge tmdb" @click="openLink(tmdbUrl)">T</button>
          </template>
        </VTooltip>
      </div>

      <div class="poster-right-actions" @click.stop>
        <VTooltip v-if="showDelete" text="删除插件记录">
          <template #activator="{ props: tooltipProps }">
            <VBtn v-bind="tooltipProps" icon="mdi-close" size="x-small" class="poster-action" :disabled="busy" @click="emit('delete', item)" />
          </template>
        </VTooltip>
        <VTooltip text="刷新">
          <template #activator="{ props: tooltipProps }">
            <VBtn v-bind="tooltipProps" icon="mdi-refresh" size="x-small" class="poster-action" :loading="busy" @click="emit('refresh', item)" />
          </template>
        </VTooltip>
        <VTooltip v-if="showEdit" text="人工识别">
          <template #activator="{ props: tooltipProps }">
            <VBtn v-bind="tooltipProps" icon="mdi-pencil" size="x-small" class="poster-action" :disabled="busy" @click="emit('edit', item)" />
          </template>
        </VTooltip>
      </div>

      <VChip v-if="Number(details.version_count || 0) > 1" class="version-chip" size="x-small" color="info">
        {{ details.version_count }}in1
      </VChip>
    </div>

    <VCardText class="card-body">
      <div class="title-slot">
        <VTooltip :text="title">
          <template #activator="{ props: tooltipProps }">
            <h3 v-bind="tooltipProps">{{ title }}</h3>
          </template>
        </VTooltip>
      </div>
      <div class="tags-slot">
        <div class="chip-row">
          <VChip size="x-small" variant="flat" :class="['info-chip', 'status-chip', `tag-${status.color}`]">{{ status.text }}</VChip>
          <VChip v-if="mediaType !== 'movie' && item.season !== null && item.season !== undefined" size="x-small" variant="flat" class="info-chip season-chip">
            {{ Number(item.season) === 0 ? '特别篇(S00)' : `第${Number(item.season)}季` }}
          </VChip>
          <VChip v-if="resolution" size="x-small" variant="flat" class="info-chip resolution-chip">{{ resolution }}</VChip>
          <VChip v-if="mediaCategory" size="x-small" variant="flat" class="info-chip category-chip">{{ mediaCategory }}</VChip>
          <VTooltip v-if="customization" :text="customization">
            <template #activator="{ props: tooltipProps }">
              <VChip v-bind="tooltipProps" size="x-small" variant="flat" class="info-chip customization-chip">{{ customizationLabel }}</VChip>
            </template>
          </VTooltip>
        </div>
      </div>
      <div class="source-slot">
        <VTooltip v-if="sourceName" :text="sourceName">
          <template #activator="{ props: tooltipProps }">
            <p v-bind="tooltipProps" class="source-name">源: {{ sourceName }}</p>
          </template>
        </VTooltip>
      </div>
      <div class="size-slot">
        <span v-if="sizeText" class="size-label">大小: {{ sizeText }}</span>
      </div>
      <div class="target-slot">
        <VTooltip v-if="plannedName && item.recognition_state !== 'unidentified'" :text="plannedName">
          <template #activator="{ props: tooltipProps }">
            <p v-bind="tooltipProps" class="target-name">{{ plannedName }}</p>
          </template>
        </VTooltip>
      </div>
      <div class="inventory-slot">
        <p v-if="plannedName" class="inventory-line" :class="inventoryClass">{{ inventoryText }}</p>
      </div>
    </VCardText>
  </VCard>
</template>

<style scoped>
.media-poster-card {
  display: flex;
  height: 100%;
  flex-direction: column;
  overflow: hidden;
  border: 3px solid transparent;
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  cursor: pointer;
  box-shadow: inset 0 0 0 1px rgba(var(--v-border-color), 0.55);
  transition: border-color 150ms ease, box-shadow 150ms ease, transform 150ms ease;
}

.media-poster-card:hover { transform: translateY(-2px); }
.media-poster-card.selected {
  border-color: #22d3ee;
  box-shadow: 0 0 0 3px rgba(34,211,238,.48), 0 8px 22px rgba(8,145,178,.24);
}

.poster-area { position: relative; aspect-ratio: 2 / 3; background: #111722; }
.poster-image, .poster-placeholder { width: 100%; height: 100%; }
.poster-placeholder { display: grid; place-items: center; color: rgba(255,255,255,.45); }
.poster-left-actions, .poster-right-actions { position: absolute; top: 10px; z-index: 2; display: flex; gap: 7px; }
.poster-left-actions { left: 10px; }
.poster-right-actions { right: 10px; }
.corner-badge { display: grid; width: 30px; height: 30px; place-items: center; border: 0; border-radius: 5px; color: #fff; font-weight: 800; line-height: 1; box-shadow: 0 2px 8px rgba(0,0,0,.32); }
button.corner-badge { cursor: pointer; }
.rollback { background: #8456e8; }
.failure { background: #df3c4f; }
.source { background: #f29a2e; }
.tmdb { background: #20b7cf; }
.poster-action { background: rgba(5,10,15,.78) !important; color: #fff !important; border-radius: 5px !important; }
.version-chip { position: absolute; right: 10px; bottom: 10px; }
.card-body {
  display: flex;
  flex: 1 1 auto;
  height: 287px;
  min-height: 287px;
  flex-direction: column;
  padding: 12px 14px 14px;
}
.title-slot,
.tags-slot,
.source-slot,
.size-slot,
.target-slot,
.inventory-slot {
  min-width: 0;
  overflow: hidden;
}
.title-slot {
  display: flex;
  max-height: 42px;
  flex: 0 0 auto;
  align-items: flex-start;
}
.card-body h3 { display: -webkit-box; margin: 0; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2; font-size: 1rem; line-height: 1.3; }
.tags-slot {
  max-height: 49px;
  flex: 0 0 auto;
  margin-top: 4px;
}
.chip-row { display: flex; min-width: 0; max-height: 49px; flex-wrap: wrap; align-items: flex-start; gap: 5px; overflow: hidden; }
.info-chip {
  width: fit-content;
  max-width: 100%;
  height: auto !important;
  min-height: 22px;
  padding: 2px 6px !important;
  border: 1px solid !important;
  border-radius: 4px !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  letter-spacing: 0 !important;
  white-space: normal !important;
  overflow: hidden;
}
.info-chip :deep(.v-chip__content) { display: block; max-width: 100%; line-height: 16px; white-space: normal; overflow-wrap: anywhere; }
.tag-info { border-color: rgba(59,130,246,.30) !important; background: rgba(59,130,246,.20) !important; color: #60a5fa !important; }
.tag-success { border-color: rgba(34,197,94,.30) !important; background: rgba(34,197,94,.20) !important; color: #4ade80 !important; }
.tag-error { border-color: rgba(220,38,38,.30) !important; background: rgba(220,38,38,.20) !important; color: #f87171 !important; }
.tag-orange { border-color: rgba(249,115,22,.30) !important; background: rgba(249,115,22,.20) !important; color: #fb923c !important; }
.tag-purple, .season-chip { border-color: rgba(124,58,237,.30) !important; background: rgba(124,58,237,.20) !important; color: #a78bfa !important; }
.resolution-chip { border-color: rgba(8,145,178,.30) !important; background: rgba(8,145,178,.20) !important; color: #22d3ee !important; }
.category-chip { border-color: rgba(139,92,246,.30) !important; background: rgba(139,92,246,.20) !important; color: #a78bfa !important; }
.customization-chip { border-color: rgba(13,148,136,.45) !important; background: rgba(13,148,136,.25) !important; color: #5eead4 !important; }
.source-name, .target-name, .inventory-line { margin: 0; overflow-wrap: anywhere; }
.source-name,
.target-name {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
}
.source-slot {
  min-height: 36px;
  max-height: 54px;
  flex: 1 1 48px;
  margin-top: 8px;
}
.source-name { color: rgba(var(--v-theme-on-surface), .58); font-size: .78rem; line-height: 1.4; -webkit-line-clamp: 3; }
.size-slot {
  display: flex;
  min-height: 22px;
  flex: 0 0 22px;
  align-items: flex-start;
  margin-top: 6px;
}
.size-label { width: fit-content; max-width: 100%; padding: 2px 6px; border: 1px solid #4b5563; border-radius: 4px; background: #374151; color: #fff; font-size: 11px; font-weight: 600; overflow-wrap: anywhere; }
.target-slot {
  min-height: 36px;
  max-height: 58px;
  flex: 1 1 48px;
  margin-top: 7px;
}
.target-name { color: rgb(var(--v-theme-info)); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .78rem; line-height: 1.4; -webkit-line-clamp: 3; }
.inventory-slot {
  display: flex;
  min-height: 27px;
  flex: 0 0 27px;
  align-items: flex-end;
  margin-top: auto;
  padding-top: 7px;
}
.inventory-line { overflow: hidden; font-size: .78rem; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.inventory-ok { color: rgb(var(--v-theme-success)); }
.inventory-missing { color: rgb(var(--v-theme-error)); }
.inventory-warning { color: rgb(var(--v-theme-warning)); }
</style>
