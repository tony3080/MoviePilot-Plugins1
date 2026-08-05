<script setup>
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
})

const currentPath = ref('/')
const parentPath = ref('')
const entries = ref([])
const loading = ref(false)
const recognizingPath = ref('')
const errorMessage = ref('')
const successMessage = ref('')

const breadcrumbs = computed(() => {
  const path = String(currentPath.value || '/').replaceAll('\\', '/')
  const parts = path.split('/').filter(Boolean)
  const items = [{ title: '/', path: '/' }]
  let cursor = ''
  for (const part of parts) {
    cursor += `/${part}`
    items.push({ title: part, path: cursor })
  }
  return items
})

function unwrap(response) {
  return response?.data ?? response
}

async function browse(path = '/') {
  loading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = unwrap(await props.api.get('plugin/RssAllInOne/files/browse', {
      params: { path },
    }))
    if (!response?.success) throw new Error(response?.message || '读取文件夹失败')
    currentPath.value = response.path || path
    parentPath.value = response.parent || ''
    entries.value = response.items || []
  } catch (error) {
    errorMessage.value = error?.message || '读取文件夹失败'
  } finally {
    loading.value = false
  }
}

async function recognize(folder) {
  if (!window.confirm(`确认递归识别文件夹“${folder.name}”中的媒体文件？`)) return
  recognizingPath.value = folder.path
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = unwrap(await props.api.post(
      'plugin/RssAllInOne/files/recognize',
      { path: folder.path },
    ))
    if (!response?.success) throw new Error(response?.message || '批量识别失败')
    successMessage.value = response.message || '识别完成'
  } catch (error) {
    errorMessage.value = error?.message || '批量识别失败'
  } finally {
    recognizingPath.value = ''
  }
}

onMounted(() => browse('/'))
</script>

<template>
  <div class="file-manager-browser">
    <div class="browser-toolbar">
      <VBtn
        icon="mdi-arrow-up"
        variant="text"
        :disabled="!parentPath || loading"
        aria-label="返回上级"
        @click="browse(parentPath)"
      />
      <VBreadcrumbs :items="breadcrumbs" density="compact" class="path-breadcrumbs">
        <template #item="{ item }">
          <button type="button" class="breadcrumb-link" @click="browse(item.path)">
            {{ item.title }}
          </button>
        </template>
      </VBreadcrumbs>
      <VSpacer />
      <VBtn
        icon="mdi-refresh"
        variant="text"
        :loading="loading"
        aria-label="刷新目录"
        @click="browse(currentPath)"
      />
    </div>

    <VAlert v-if="errorMessage" type="error" variant="tonal" density="compact" class="browser-alert">
      {{ errorMessage }}
    </VAlert>
    <VAlert v-if="successMessage" type="success" variant="tonal" density="compact" class="browser-alert">
      {{ successMessage }}
    </VAlert>

    <div class="entry-list">
      <div v-for="entry in entries" :key="entry.path" class="entry-row">
        <button
          v-if="entry.type === 'dir'"
          type="button"
          class="entry-name entry-link"
          @click="browse(entry.path)"
        >
          <VIcon icon="mdi-folder" color="amber" size="22" />
          <span>{{ entry.name }}</span>
        </button>
        <div v-else class="entry-name">
          <VIcon icon="mdi-file-outline" color="blue-grey-lighten-1" size="22" />
          <span>{{ entry.name }}</span>
        </div>
        <VBtn
          v-if="entry.type === 'dir'"
          color="primary"
          variant="tonal"
          size="small"
          prepend-icon="mdi-text-recognition"
          :loading="recognizingPath === entry.path"
          :disabled="Boolean(recognizingPath)"
          @click="recognize(entry)"
        >
          批量识别
        </VBtn>
      </div>
    </div>

    <VProgressLinear v-if="loading" indeterminate color="primary" />
    <VEmptyState
      v-else-if="!entries.length"
      icon="mdi-folder-open-outline"
      title="当前目录为空"
    />
  </div>
</template>

<style scoped>
.file-manager-browser { min-height: 420px; }
.browser-toolbar {
  display: flex;
  align-items: center;
  min-height: 52px;
  border-bottom: 1px solid rgba(var(--v-border-color), .45);
}
.path-breadcrumbs { min-width: 0; padding-inline: 4px; }
.breadcrumb-link {
  color: rgb(var(--v-theme-primary));
  background: none;
  border: 0;
  cursor: pointer;
  font: inherit;
}
.browser-alert { margin: 12px 0; }
.entry-list { display: grid; }
.entry-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 54px;
  padding: 7px 10px;
  border-bottom: 1px solid rgba(var(--v-border-color), .35);
}
.entry-row:hover { background: rgba(var(--v-theme-on-surface), .035); }
.entry-name {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
  color: inherit;
  text-align: left;
}
.entry-link {
  cursor: pointer;
  background: none;
  border: 0;
}
.entry-name span { overflow-wrap: anywhere; }
</style>
