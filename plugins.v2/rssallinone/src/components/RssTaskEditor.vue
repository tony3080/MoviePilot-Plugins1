<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  downloaders: { type: Array, default: () => [] },
  sites: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  testingTaskId: { type: String, default: '' },
  runningTaskId: { type: String, default: '' },
  rssEnabled: { type: Boolean, default: true },
  controlling: { type: Boolean, default: false },
})

const emit = defineEmits(['save', 'reload', 'test', 'run', 'control'])

const tasks = ref([])
const expanded = ref([])

const booleanOptions = [
  { key: 'pause_on_add', label: '添加种子时暂停' },
  { key: 'push_torrent_file', label: '推送种子文件' },
  { key: 'recognize_cn', label: '识别国语' },
  { key: 'recognize_fx', label: '识别特效' },
  { key: 'add_chinese_title', label: '添加中文标题' },
  { key: 'import_enabled', label: '入库' },
  { key: 'realtime_hardlink_enabled', label: '完成后创建实时硬链接' },
  { key: 'rename_enabled', label: '重命名' },
  { key: 'download_enabled', label: '下载' },
  { key: 'delete_files', label: '删除文件' },
  { key: 'hr_enabled', label: 'HR保护' },
]

const taskTypeOptions = [
  { title: 'RSS任务', value: 'rss' },
  { title: '手动添加', value: 'manual' },
]

const downloaderOptions = computed(() => props.downloaders.map(item => ({
  title: `${item.name}${item.default ? ' · 默认' : ''}${item.ready ? '' : ' · 未就绪'}`,
  value: item.name,
  disabled: !item.enabled,
})))

const siteOptions = computed(() => [
  { title: '不使用站点标签识别', value: '' },
  ...props.sites.map(item => ({
    title: `${item.name || item.domain}${item.enabled ? '' : ' · 未启用'}`,
    value: String(item.id || ''),
  })),
])

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function newId() {
  return globalThis.crypto?.randomUUID?.().replaceAll('-', '')
    || `rss-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function defaultConfig() {
  return {
    task_type: 'rss',
    rss_url: '',
    qb_downloader: '',
    rss_cron: '*/10 * * * *',
    save_path: '',
    qb_category: '',
    name_contains: '',
    start_cron: '*/5 * * * *',
    delete_after_minutes: 0,
    upload_limit_kbps: 0,
    rename_rules: '',
    site_id: '',
    cn_keywords: '国语,国配',
    pause_on_add: true,
    push_torrent_file: false,
    recognize_cn: false,
    recognize_fx: false,
    add_chinese_title: false,
    import_enabled: true,
    realtime_hardlink_enabled: false,
    realtime_source_root: '',
    realtime_link_root: '',
    rename_enabled: false,
    download_enabled: true,
    delete_files: false,
    hr_enabled: false,
    hr_cron: '30 3 * * *',
    local_path: '',
    process_local_files: false,
    local_initialized: false,
    local_initialized_at: '',
    local_path_fingerprint: '',
    query_interval: 60,
  }
}

function normalizeTask(item = {}, index = 0) {
  return {
    ...clone(item),
    id: item.id || newId(),
    name: item.name || `RSS任务 ${index + 1}`,
    enabled: item.enabled !== false && item.enabled !== 0,
    position: index,
    config: {
      ...defaultConfig(),
      ...(clone(item.config || {})),
    },
  }
}

function addTask() {
  const task = normalizeTask({}, tasks.value.length)
  tasks.value.push(task)
  expanded.value = [...expanded.value, task.id]
}

function removeTask(index) {
  const [removed] = tasks.value.splice(index, 1)
  expanded.value = expanded.value.filter(id => id !== removed?.id)
  tasks.value.forEach((task, position) => { task.position = position })
}

function saveTasks() {
  emit('save', tasks.value.map((task, position) => ({
    ...clone(task),
    position,
  })))
}

function testTask(task, position) {
  emit('test', {
    ...clone(task),
    position,
  })
}

function keepExpanded(taskId) {
  if (!taskId || expanded.value.includes(taskId)) return
  expanded.value = [...expanded.value, taskId]
}

watch(
  () => props.items,
  value => {
    tasks.value = (value || []).map(normalizeTask)
    expanded.value = tasks.value.length === 1 ? [tasks.value[0].id] : []
  },
  { immediate: true, deep: true },
)
</script>

<template>
  <div class="rss-editor">
    <div class="rss-toolbar">
      <span class="text-caption text-medium-emphasis">{{ tasks.length }} 条任务</span>
      <VSpacer />
      <VBtn
        :prepend-icon="rssEnabled ? 'mdi-pause-circle-outline' : 'mdi-play-circle-outline'"
        :color="rssEnabled ? 'warning' : 'success'"
        variant="tonal"
        :loading="controlling"
        @click="emit('control', !rssEnabled)"
      >
        {{ rssEnabled ? '暂停 RSS 调度' : '恢复 RSS 调度' }}
      </VBtn>
      <VTooltip text="重新读取">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-refresh"
            variant="text"
            :loading="loading"
            aria-label="重新读取"
            @click="emit('reload')"
          />
        </template>
      </VTooltip>
      <VBtn prepend-icon="mdi-plus" variant="text" @click="addTask">
        添加任务
      </VBtn>
      <VBtn
        prepend-icon="mdi-content-save"
        color="primary"
        variant="tonal"
        :loading="loading"
        @click="saveTasks"
      >
        保存
      </VBtn>
    </div>

    <VAlert v-if="tasks.length === 0" type="info" variant="tonal">
      暂无 RSS 任务
    </VAlert>

    <VExpansionPanels v-else v-model="expanded" multiple class="task-panels">
      <VExpansionPanel v-for="(task, index) in tasks" :key="task.id" :value="task.id">
        <VExpansionPanelTitle>
          <div class="task-title">
            <VSwitch
              v-model="task.enabled"
              density="compact"
              hide-details
              color="primary"
              @click.stop
            />
            <strong>{{ task.name || `RSS任务 ${index + 1}` }}</strong>
            <VChip v-if="task.config.qb_category" size="small" variant="tonal">
              {{ task.config.qb_category }}
            </VChip>
            <VSpacer />
            <VTooltip text="立即执行已保存配置">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  icon="mdi-play-circle-outline"
                  size="small"
                  variant="text"
                  color="success"
                  :loading="runningTaskId === task.id"
                  :disabled="(task.config.task_type === 'rss' && !rssEnabled) || !task.enabled || (task.config.task_type === 'rss' && !String(task.config.rss_url || '').trim())"
                  aria-label="立即执行 RSS"
                  @click.stop="emit('run', task)"
                />
              </template>
            </VTooltip>
            <VTooltip text="测试 RSS">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  icon="mdi-flask-outline"
                  size="small"
                  variant="text"
                  color="primary"
                  :loading="testingTaskId === task.id"
                  :disabled="task.config.task_type !== 'rss' || !String(task.config.rss_url || '').trim()"
                  aria-label="测试 RSS"
                  @click.stop="testTask(task, index)"
                />
              </template>
            </VTooltip>
            <VTooltip text="删除任务">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  icon="mdi-delete-outline"
                  size="small"
                  variant="text"
                  color="error"
                  aria-label="删除任务"
                  @click.stop="removeTask(index)"
                />
              </template>
            </VTooltip>
          </div>
        </VExpansionPanelTitle>
        <VExpansionPanelText>
          <VRow dense>
            <VCol cols="12" md="4">
              <VTextField v-model="task.name" label="任务名称" />
            </VCol>
            <VCol cols="12" md="4">
              <VSelect
                v-model="task.config.task_type"
                :items="taskTypeOptions"
                label="任务类型"
                @click.stop
                @mousedown.stop
                @update:model-value="keepExpanded(task.id)"
              />
            </VCol>
            <VCol v-if="task.config.task_type === 'rss'" cols="12" md="4">
              <VTextField v-model="task.config.rss_url" label="RSS URL" />
            </VCol>
            <VCol cols="12" md="4">
              <VSelect
                v-model="task.config.qb_downloader"
                :items="downloaderOptions"
                label="QB下载器"
              />
            </VCol>
            <VCol cols="12" md="4">
              <VTextField v-model="task.config.qb_category" label="QB分类" />
            </VCol>
            <VCol v-if="task.config.task_type === 'rss'" cols="12" md="4">
              <VTextField v-model="task.config.save_path" label="保存路径" />
            </VCol>
            <VCol v-if="task.config.task_type === 'rss'" cols="12" md="6">
              <VTextField v-model="task.config.rss_cron" label="RSS周期 (CRON)" />
            </VCol>
            <VCol v-if="task.config.task_type === 'rss'" cols="12" md="6">
              <VTextField v-model="task.config.start_cron" label="开始任务 CRON" />
            </VCol>
            <VCol v-if="task.config.task_type === 'rss'" cols="12" md="6">
              <VTextField v-model="task.config.name_contains" label="限制条件 (名称包含)" />
            </VCol>
            <template v-if="task.config.task_type === 'manual'">
              <VCol cols="12" md="6">
                <VTextField v-model="task.config.local_path" label="本地目录" placeholder="/MP/机械UB收藏" />
              </VCol>
              <VCol cols="12" md="3">
                <VTextField v-model.number="task.config.query_interval" label="查询间隔（秒）" type="number" min="1" />
              </VCol>
              <VCol cols="12" md="3" class="d-flex align-center">
                <VSwitch v-model="task.config.process_local_files" label="处理本地文件" density="compact" color="primary" hide-details />
              </VCol>
              <VCol cols="12">
                <VAlert v-if="task.config.local_initialized" type="success" variant="tonal" density="compact">
                  本地目录已完成首次处理（{{ task.config.local_initialized_at || '已初始化' }}）
                </VAlert>
              </VCol>
            </template>
            <VCol v-if="task.config.task_type === 'rss'" cols="12" md="3">
              <VTextField
                v-model.number="task.config.delete_after_minutes"
                label="完成后删除任务 (分钟)"
                type="number"
                min="0"
                :disabled="task.config.hr_enabled"
                :hint="task.config.hr_enabled ? '勾选 HR 后此项无效' : ''"
                :persistent-hint="task.config.hr_enabled"
              />
            </VCol>
            <VCol v-if="task.config.task_type === 'rss'" cols="12" md="3">
              <VTextField
                v-model="task.config.hr_cron"
                label="HR扫描 CRON"
                placeholder="30 3 * * *"
                :disabled="!task.config.hr_enabled"
                hint="勾选 HR 后按此 CRON 对照彩虹岛 HR 名单删除任务"
                :persistent-hint="task.config.hr_enabled"
              />
            </VCol>
            <VCol v-if="task.config.task_type === 'rss'" cols="12" md="3">
              <VTextField
                v-model.number="task.config.upload_limit_kbps"
                label="上传限速 (kb/s)"
                type="number"
                min="0"
              />
            </VCol>
            <VCol cols="12" md="6">
              <VTextarea
                v-model="task.config.rename_rules"
                :label="task.config.task_type === 'manual' ? '重命名规则（可选）' : '重命名规则'"
                rows="3"
                auto-grow
              />
            </VCol>
            <VCol cols="12" md="6">
              <VSelect
                v-model="task.config.site_id"
                :items="siteOptions"
                label="站点访问身份"
              />
            </VCol>
            <VCol v-if="task.config.task_type === 'rss'" cols="12" md="6">
              <VTextField v-model="task.config.cn_keywords" label="国语关键词" />
            </VCol>
            <VCol v-if="task.config.task_type === 'rss'" cols="12" md="6">
              <VTextField
                v-model="task.config.realtime_source_root"
                label="实时硬链接源根目录"
                placeholder="/SSD/QB目录/REMUX/CHD"
                :disabled="!task.config.realtime_hardlink_enabled"
              />
            </VCol>
            <VCol v-if="task.config.task_type === 'rss'" cols="12" md="6">
              <VTextField
                v-model="task.config.realtime_link_root"
                label="实时硬链接目标根目录"
                placeholder="/SSD/QB目录/REMUX/CHDlink"
                :disabled="!task.config.realtime_hardlink_enabled"
              />
            </VCol>
          </VRow>

          <VDivider class="mb-3" />
          <div class="switch-grid">
            <VSwitch
              v-for="option in booleanOptions"
              :key="option.key"
              v-if="task.config.task_type === 'rss' || !['pause_on_add','push_torrent_file','recognize_cn','recognize_fx','add_chinese_title','rename_enabled','download_enabled','delete_files','hr_enabled'].includes(option.key)"
              v-model="task.config[option.key]"
              :label="option.label"
              density="compact"
              color="primary"
              hide-details
            />
          </div>
        </VExpansionPanelText>
      </VExpansionPanel>
    </VExpansionPanels>
  </div>
</template>

<style scoped>
.rss-editor {
  min-width: 0;
}

.rss-toolbar,
.task-title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}

.rss-toolbar {
  margin-bottom: 12px;
}

.task-title {
  width: 100%;
}

.task-title strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-panels :deep(.v-expansion-panel) {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 6px;
}

.switch-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px 16px;
}

@media (max-width: 900px) {
  .rss-toolbar {
    flex-wrap: wrap;
  }

  .switch-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .switch-grid {
    grid-template-columns: 1fr;
  }
}
</style>
