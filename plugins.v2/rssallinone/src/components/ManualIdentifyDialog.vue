<script setup>
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  modelValue: Boolean,
  item: { type: Object, default: null },
  categories: { type: Array, default: () => [] },
  loading: Boolean,
})

const emit = defineEmits(['update:modelValue', 'save'])
const form = reactive({ media_type: 'tv', tmdb_id: '', season: 1, category: '' })
const open = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})
const categoryItems = computed(() => [
  { title: '自动分类（MoviePilot）', value: '' },
  ...props.categories.map(value => ({ title: value, value })),
])
const automaticCategory = computed(() => props.item?.details?.automatic_category || props.item?.category || '未分类')

watch(() => [props.modelValue, props.item], ([visible]) => {
  if (!visible || !props.item) return
  const override = props.item.details?.manual_override || {}
  form.media_type = override.media_type || props.item.media_type || 'tv'
  form.tmdb_id = override.tmdb_id || props.item.tmdb_id || ''
  form.season = override.season ?? props.item.season ?? 1
  form.category = override.category || ''
}, { immediate: true })

function submit() {
  emit('save', {
    downloader_id: props.item?.downloader_id,
    info_hash: props.item?.info_hash,
    media_type: form.media_type,
    tmdb_id: Number(form.tmdb_id || 0),
    season: form.media_type === 'tv' ? Number(form.season || 0) : null,
    category: form.category,
  })
}
</script>

<template>
  <VDialog v-model="open" max-width="520" persistent>
    <VCard class="identify-dialog">
      <VCardTitle class="dialog-title">
        <VIcon icon="mdi-movie-edit-outline" color="primary" />
        <span>人工识别</span>
        <VSpacer />
        <VBtn icon="mdi-close" variant="text" :disabled="loading" aria-label="关闭" @click="open = false" />
      </VCardTitle>
      <VDivider />
      <VCardText class="dialog-form">
        <p class="source-title">{{ item?.name || item?.source_name || item?.title }}</p>
        <VBtnToggle v-model="form.media_type" mandatory divided color="primary" variant="outlined" class="type-toggle">
          <VBtn value="movie"><VIcon icon="mdi-movie-outline" class="me-2" />电影</VBtn>
          <VBtn value="tv"><VIcon icon="mdi-television-classic" class="me-2" />电视剧</VBtn>
        </VBtnToggle>
        <VTextField
          v-model="form.tmdb_id"
          type="number"
          min="1"
          label="TMDB ID"
          prepend-inner-icon="mdi-database-search-outline"
          hide-details="auto"
        />
        <VTextField
          v-if="form.media_type === 'tv'"
          v-model="form.season"
          type="number"
          min="0"
          label="季号"
          prepend-inner-icon="mdi-format-list-numbered"
          hint="特别篇填写 0"
          persistent-hint
        />
        <VSelect
          v-model="form.category"
          :items="categoryItems"
          label="分类"
          prepend-inner-icon="mdi-folder-outline"
          hide-details="auto"
        />
        <div class="automatic-category">
          <span>MoviePilot 自动分类</span>
          <strong>{{ automaticCategory }}</strong>
        </div>
      </VCardText>
      <VDivider />
      <VCardActions class="dialog-actions">
        <VBtn variant="text" :disabled="loading" @click="open = false">取消</VBtn>
        <VBtn
          color="primary"
          variant="flat"
          prepend-icon="mdi-check"
          :loading="loading"
          :disabled="!Number(form.tmdb_id || 0)"
          @click="submit"
        >
          重新识别
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.identify-dialog { border-radius: 8px; }
.dialog-title { display: flex; min-height: 58px; align-items: center; gap: 10px; }
.dialog-form { display: grid; gap: 16px; padding-top: 20px; }
.source-title { margin: 0; overflow-wrap: anywhere; color: rgba(var(--v-theme-on-surface), .68); font-size: .82rem; }
.type-toggle { width: 100%; }
.type-toggle :deep(.v-btn) { flex: 1 1 50%; }
.automatic-category { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 12px; border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 6px; font-size: .82rem; }
.automatic-category span { color: rgba(var(--v-theme-on-surface), .62); }
.dialog-actions { justify-content: flex-end; padding: 12px 18px; }
</style>
