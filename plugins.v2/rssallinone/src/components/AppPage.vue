<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import RssTaskEditor from './RssTaskEditor.vue'
import MediaPosterCard from './MediaPosterCard.vue'
import ManualIdentifyDialog from './ManualIdentifyDialog.vue'

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
const categoryOptions = ref([])
const selectedKeys = ref([])
const itemBusyKey = ref('')
const batchAction = ref('')
const identifyDialog = ref(false)
const identifyItem = ref(null)
const mediaState = ref('')
const mediaType = ref('')
const mediaRssTaskIds = ref([])
const qbDownloaders = ref([])
const qbDownloader = ref('')
const qbView = ref('')
const qbKeyword = ref('')
const qbTask = ref(null)
const rssTestingTaskId = ref('')
const rssRunningTaskId = ref('')
const rssBackgroundTask = ref(null)
const rssControlLoading = ref(false)
const rssTestDialog = ref(false)
const rssTestResult = ref(null)
let qbPollTimer = null
let rssPollTimer = null

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
  { title: '资源信息', key: 'resource_info', minWidth: 280 },
  { title: '库存', key: 'inventory_state', width: 110 },
  { title: '识别', key: 'recognition_state', width: 110 },
  { title: '下载状态', key: 'state', width: 120 },
  { title: '进度', key: 'progress', width: 100 },
  { title: '节点', key: 'downloader_id', width: 130 },
  { title: '分类', key: 'category', width: 110 },
  { title: '双阶段映射', key: 'mapping_summary', width: 150 },
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

const rssTestHeaders = [
  { title: '状态', key: 'status', width: 130 },
  { title: '标题', key: 'title', minWidth: 300 },
  { title: '种子 ID', key: 'torrent_id', width: 100 },
  { title: '发布时间', key: 'published', minWidth: 180 },
  { title: '种子链接', key: 'enclosure_url_masked', minWidth: 300 },
  { title: '详情链接', key: 'detail_url_masked', minWidth: 300 },
  { title: '原因', key: 'reason', minWidth: 220 },
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
const rssEnabled = computed(() => overview.value.plugin?.rss_enabled !== false)
const rssTaskFilterOptions = computed(() => (rssTasks.value || []).map(task => ({
  title: task.name || task.id,
  value: String(task.id || ''),
})).filter(item => item.value))
const selectedItems = computed(() => rows.value.filter(
  item => selectedKeys.value.includes(itemKey(item)),
))
const selectedStates = computed(() => selectedItems.value.map(item => item.state || ''))
const selectionAllImported = computed(() => (
  selectedItems.value.length > 0
  && selectedStates.value.every(state => state === 'imported')
))
const selectionCanQueue = computed(() => (
  selectedItems.value.length > 0
  && selectedStates.value.every(state => ['identified', 'rolled_back'].includes(state))
))
const selectionCanImport = computed(() => (
  selectedItems.value.length > 0
  && selectedStates.value.every(state => ['identified', 'pending', 'rolled_back'].includes(state))
))
const selectionCanDeleteSource = computed(() => (
  selectedItems.value.length > 0
  && selectedStates.value.every(state => state !== 'imported')
))
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

const rssTestLabels = {
  ready: '可处理',
  filtered: '已过滤',
  missing_enclosure: '缺少种子链接',
  duplicate: '重复',
  invalid: '无效',
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

function uniqueTexts(values) {
  const result = []
  for (const value of values || []) {
    const text = String(value || '').trim()
    if (text && !result.some(item => item.toLocaleLowerCase() === text.toLocaleLowerCase())) {
      result.push(text)
    }
  }
  return result
}

function torrentRecognition(item) {
  const expectedFiles = item.details?.inventory_plan?.expected_files || []
  return {
    tokens: uniqueTexts(expectedFiles.flatMap(file => file.recognition?.resource_tokens || [])),
    words: uniqueTexts(expectedFiles.flatMap(file => file.recognition?.apply_words || [])),
    customizations: uniqueTexts(expectedFiles.map(file => file.recognition?.customization || '')),
    inherited: uniqueTexts(expectedFiles.flatMap(file => file.recognition?.inherited_fields || [])),
  }
}

function itemKey(item) {
  return item.row_key || item.id || `${item.downloader_id}:${item.info_hash}`
}

function toggleSelected(item) {
  const key = itemKey(item)
  selectedKeys.value = selectedKeys.value.includes(key)
    ? selectedKeys.value.filter(value => value !== key)
    : [...selectedKeys.value, key]
}

function selectAllVisible() {
  selectedKeys.value = rows.value.map(itemKey)
}

function clearSelection() {
  selectedKeys.value = []
}

async function reloadForFilter() {
  clearSelection()
  await loadActive()
}

async function loadCategories() {
  const response = unwrap(await props.api.get('plugin/RssAllInOne/categories'))
  categoryOptions.value = response?.items || []
}

async function loadOverview() {
  const response = unwrap(await props.api.get('plugin/RssAllInOne/overview'))
  overview.value = response || overview.value
  if (response?.qb_task?.id && !qbTask.value?.id) {
    qbTask.value = response.qb_task
    scheduleQbPoll(response.qb_task.id)
  }
  if (response?.rss_task?.id && !rssBackgroundTask.value?.id) {
    rssBackgroundTask.value = response.rss_task
    scheduleRssPoll(response.rss_task.id)
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

async function loadRssTasks() {
  const response = unwrap(await props.api.get('plugin/RssAllInOne/rss/tasks', {
    params: { offset: 0, limit: 100 },
  }))
  rssTasks.value = response?.items || []
  return response
}

async function loadActive() {
  loading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await loadOverview()
    if (['library', 'qb'].includes(activeTab.value)) {
      await loadCategories()
    }
    if (activeTab.value === 'library') {
      await loadRssTasks()
    }
    if (activeTab.value === 'overview') {
      rows.value = []
      total.value = 0
      return
    }

    if (activeTab.value === 'vt' && vtTab.value === 'rss_tasks') {
      const [response] = await Promise.all([
        loadRssTasks(),
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
        rss_task_ids: mediaRssTaskIds.value.join(','),
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
    } else if (activeTab.value === 'library') {
      rows.value = items.map(item => ({
        ...item,
        row_key: item.id,
        poster: item.poster || item.details?.media?.poster_path || '',
        inventory_state: item.details?.inventory?.folder_status === 'exists'
          ? (Number(item.details?.inventory?.missing_count || 0) ? 'partial' : 'exists')
          : item.details?.inventory?.folder_status || 'missing',
        recognition_state: item.state === 'unidentified' ? 'unidentified' : 'identified',
      }))
    } else if (activeTab.value === 'qb') {
      rows.value = items.map(item => {
        const recognition = torrentRecognition(item)
        const mappings = item.details?.file_mappings || []
        const pendingMappings = mappings.filter(mapping => !mapping.inventory_exists).length
        return {
          ...item,
          row_key: `${item.downloader_id}:${item.info_hash}`,
          qb_category: item.category,
          media_category: item.details?.path_plan?.category || item.details?.automatic_category || '',
          target_name: item.details?.path_plan?.inventory_files?.[0]?.path || '',
          link_target: item.details?.path_plan?.link_files?.[0]?.path || '',
          resource_tokens: recognition.tokens,
          applied_words: recognition.words,
          customizations: recognition.customizations,
          inherited_meta_fields: recognition.inherited,
          mapping_summary: mappings.length
            ? `${mappings.length} 个 · 待建 ${pendingMappings}`
            : '未生成',
        }
      })
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

async function testRssTask(task) {
  rssTestingTaskId.value = String(task?.id || '')
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/rss/test', { task }),
    )
    if (!response?.success || !response?.result) {
      throw new Error(response?.message || 'RSS 测试失败')
    }
    rssTestResult.value = response.result
    rssTestDialog.value = true
    successMessage.value = response.message || 'RSS 测试完成'
  } catch (error) {
    rssTestResult.value = null
    errorMessage.value = error?.message || 'RSS 测试失败'
  } finally {
    rssTestingTaskId.value = ''
  }
}

async function controlRss(enabled) {
  rssControlLoading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/rss/control', { enabled }),
    )
    if (!response?.success) throw new Error(response?.message || 'RSS 调度开关保存失败')
    overview.value.plugin = {
      ...(overview.value.plugin || {}),
      rss_enabled: Boolean(response.enabled),
    }
    successMessage.value = response.message || 'RSS 调度状态已更新'
  } catch (error) {
    errorMessage.value = error?.message || 'RSS 调度开关保存失败'
  } finally {
    rssControlLoading.value = false
  }
}

async function runRssTask(task) {
  const configuredTaskId = String(task?.id || '')
  rssRunningTaskId.value = configuredTaskId
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/rss/run', { task_id: configuredTaskId }),
    )
    if (!response?.success || !response?.task_id) {
      throw new Error(response?.message || 'RSS 执行启动失败')
    }
    rssBackgroundTask.value = {
      id: response.task_id,
      state: 'running',
      processed: 0,
      total: 0,
    }
    successMessage.value = response.message || 'RSS 执行已启动'
    scheduleRssPoll(response.task_id)
  } catch (error) {
    rssRunningTaskId.value = ''
    errorMessage.value = error?.message || 'RSS 执行启动失败'
  }
}

function scheduleRssPoll(taskId) {
  if (!taskId) return
  window.clearTimeout(rssPollTimer)
  rssPollTimer = window.setTimeout(() => pollRssTask(taskId), 1200)
}

async function pollRssTask(taskId) {
  try {
    const response = unwrap(
      await props.api.get(`plugin/RssAllInOne/tasks/${taskId}`),
    )
    if (!response?.success || !response?.task) return
    rssBackgroundTask.value = response.task
    if (['queued', 'running'].includes(response.task.state)) {
      scheduleRssPoll(taskId)
      return
    }
    const result = response.task.result || {}
    successMessage.value = response.task.state === 'succeeded'
      ? `RSS 执行完成：加入 ${result.queued || 0}，已存在 ${result.existing || 0}，来源重复 ${result.duplicate_source || 0}，失败 ${result.failed || 0}`
      : `RSS 执行已${response.task.state === 'cancelled' ? '停止' : '结束'}`
    rssRunningTaskId.value = ''
    await loadOverview()
  } catch (error) {
    rssRunningTaskId.value = ''
    errorMessage.value = error?.message || '读取 RSS 执行进度失败'
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

function openIdentify(item) {
  identifyItem.value = item
  identifyDialog.value = true
}

async function refreshItem(item) {
  const key = itemKey(item)
  if (activeTab.value === 'library' && !item.id) {
    errorMessage.value = '该记录缺少媒体 ID，暂时无法刷新'
    return
  }
  if (activeTab.value !== 'library' && (!item.downloader_id || !item.info_hash)) {
    errorMessage.value = '该记录没有关联的 qB 任务，暂时无法重新识别'
    return
  }
  itemBusyKey.value = key
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = activeTab.value === 'library'
      ? unwrap(await props.api.post('plugin/RssAllInOne/media/refresh', {
        media_id: item.id,
      }))
      : unwrap(await props.api.post('plugin/RssAllInOne/qb/item/refresh', {
        downloader_id: item.downloader_id,
        info_hash: item.info_hash,
      }))
    if (!response?.success) throw new Error(response?.message || '刷新失败')
    successMessage.value = response.message || '任务已刷新'
    await loadActive()
  } catch (error) {
    errorMessage.value = error?.message || '刷新失败'
  } finally {
    itemBusyKey.value = ''
  }
}

async function saveManualIdentify(payload) {
  const key = itemKey(identifyItem.value || payload)
  itemBusyKey.value = key
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/qb/item/identify', payload),
    )
    if (!response?.success) throw new Error(response?.message || '人工识别失败')
    identifyDialog.value = false
    identifyItem.value = null
    successMessage.value = response.message || '已按指定信息重新识别'
    await loadActive()
  } catch (error) {
    errorMessage.value = error?.message || '人工识别失败'
  } finally {
    itemBusyKey.value = ''
  }
}

async function deleteMediaRecord(item) {
  if (!window.confirm(`只删除插件记录“${item.title || item.source_name || ''}”？`)) return
  itemBusyKey.value = itemKey(item)
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/media/delete', { media_id: item.id }),
    )
    if (!response?.success) throw new Error(response?.message || '删除记录失败')
    successMessage.value = response.message || '媒体记录已删除'
    selectedKeys.value = selectedKeys.value.filter(value => value !== itemKey(item))
    await loadActive()
  } catch (error) {
    errorMessage.value = error?.message || '删除记录失败'
  } finally {
    itemBusyKey.value = ''
  }
}

const mediaActionLabels = {
  queue_import: '转待入库',
  import: '入库',
  delete_source: '删源',
  delete_hardlinks: '只删硬链接',
  delete_both: '删除硬链接和源文件',
}

async function runMediaAction(action) {
  if (!selectedItems.value.length || batchAction.value) return
  const label = mediaActionLabels[action] || action
  const destructive = ['delete_source', 'delete_hardlinks', 'delete_both'].includes(action)
  if (destructive) {
    const warning = action === 'delete_source'
      ? '将删除选中卡片持久化映射中的源文件，并移除插件记录；不会删除硬链接。'
      : action === 'delete_hardlinks'
        ? '只删除本插件实际创建的硬链接；库存已存在或非插件创建的目标会保留。项目将回退到识别列表。'
        : '将删除本插件实际创建的硬链接和映射中的源文件，并移除插件记录。此操作不可恢复。'
    if (!window.confirm(`${warning}\n\n确定对 ${selectedItems.value.length} 项执行“${label}”吗？`)) return
  }
  batchAction.value = action
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const payload = {
      action,
      media_ids: selectedItems.value.map(item => item.id),
    }
    if (destructive) payload.confirm = `CONFIRM_${action.toUpperCase()}`
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/media/action', payload),
    )
    if (!response?.success && !response?.partial) {
      throw new Error(response?.message || `${label}失败`)
    }
    if (response.partial) {
      const failures = (response.results || [])
        .filter(item => !item.success)
        .slice(0, 3)
        .map(item => item.message)
        .join('；')
      errorMessage.value = `${response.message}${failures ? `：${failures}` : ''}`
    } else {
      successMessage.value = response.message || `${label}完成`
    }
    clearSelection()
    await loadActive()
  } catch (error) {
    errorMessage.value = error?.message || `${label}失败`
  } finally {
    batchAction.value = ''
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
  if (totalFiles > 0 && ['exists', 'partial'].includes(item.inventory_state)) {
    return `已存在 ${existsCount}/${totalFiles}`
  }
  if (totalFiles > 0 && item.inventory_state === 'missing') {
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

function rssTestColor(state) {
  return {
    ready: 'success',
    filtered: 'default',
    missing_enclosure: 'warning',
    duplicate: 'info',
    invalid: 'error',
  }[state] || 'default'
}

watch(activeTab, async value => {
  clearSelection()
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
  clearSelection()
  if (activeTab.value === 'vt') loadActive()
})
watch([mediaState, mediaType, mediaRssTaskIds], () => {
  clearSelection()
  if (activeTab.value === 'library') loadActive()
})
watch([qbDownloader, qbView], () => {
  clearSelection()
  if (activeTab.value === 'qb') loadActive()
})
onMounted(loadActive)
onBeforeUnmount(() => {
  window.clearTimeout(qbPollTimer)
  window.clearTimeout(rssPollTimer)
})
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
              { title: '已回退', value: 'rolled_back' },
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
          <VSelect
            v-model="mediaRssTaskIds"
            :items="rssTaskFilterOptions"
            label="RSS任务"
            multiple
            chips
            closable-chips
            clearable
            density="compact"
            hide-details
            class="rss-task-filter"
          />
          <span class="text-caption text-medium-emphasis">{{ total }} 项</span>
        </div>
        <div v-if="rows.length" class="selection-bar">
          <span>已选 {{ selectedKeys.length }} 项</span>
          <VBtn size="small" variant="text" @click="selectAllVisible">全选当前</VBtn>
          <VBtn size="small" variant="text" :disabled="!selectedKeys.length" @click="selectedKeys = []">取消选择</VBtn>
          <VSpacer />
          <div v-if="!selectionAllImported" class="selection-actions">
            <VBtn
              size="small"
              variant="tonal"
              color="purple"
              prepend-icon="mdi-tray-arrow-down"
              :disabled="!selectionCanQueue || Boolean(batchAction)"
              :loading="batchAction === 'queue_import'"
              @click="runMediaAction('queue_import')"
            >转待入库</VBtn>
            <VBtn
              size="small"
              variant="tonal"
              color="primary"
              prepend-icon="mdi-link-variant-plus"
              :disabled="!selectionCanImport || Boolean(batchAction)"
              :loading="batchAction === 'import'"
              @click="runMediaAction('import')"
            >入库</VBtn>
            <VBtn
              size="small"
              variant="tonal"
              color="error"
              prepend-icon="mdi-delete-alert-outline"
              :disabled="!selectionCanDeleteSource || Boolean(batchAction)"
              :loading="batchAction === 'delete_source'"
              @click="runMediaAction('delete_source')"
            >删源</VBtn>
          </div>
          <div v-else class="selection-actions">
            <VBtn
              size="small"
              variant="tonal"
              color="warning"
              prepend-icon="mdi-link-variant-off"
              :disabled="Boolean(batchAction)"
              :loading="batchAction === 'delete_hardlinks'"
              @click="runMediaAction('delete_hardlinks')"
            >只删硬链接</VBtn>
            <VBtn
              size="small"
              variant="tonal"
              color="error"
              prepend-icon="mdi-delete-forever-outline"
              :disabled="Boolean(batchAction)"
              :loading="batchAction === 'delete_both'"
              @click="runMediaAction('delete_both')"
            >删除硬链接和源文件</VBtn>
          </div>
        </div>
        <div v-if="rows.length" class="poster-grid">
          <MediaPosterCard
            v-for="item in rows"
            :key="itemKey(item)"
            :item="item"
            :mode="item.state === 'imported' ? 'imported' : 'pending'"
            :selected="selectedKeys.includes(itemKey(item))"
            :busy="itemBusyKey === itemKey(item)"
            @toggle="toggleSelected"
            @refresh="refreshItem"
            @edit="openIdentify"
            @delete="deleteMediaRecord"
          />
        </div>
        <VEmptyState v-else-if="!loading" icon="mdi-movie-open-outline" title="暂无媒体记录" />
        <VProgressLinear v-if="loading" indeterminate color="primary" />
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
            @keyup.enter="reloadForFilter"
            @click:clear="reloadForFilter"
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
        <div v-if="rows.length" class="selection-bar">
          <span>已选 {{ selectedKeys.length }} 项</span>
          <VBtn size="small" variant="text" @click="selectAllVisible">全选当前</VBtn>
          <VBtn size="small" variant="text" :disabled="!selectedKeys.length" @click="selectedKeys = []">取消选择</VBtn>
        </div>
        <div v-if="rows.length" class="poster-grid">
          <MediaPosterCard
            v-for="item in rows"
            :key="itemKey(item)"
            :item="item"
            mode="qb"
            :selected="selectedKeys.includes(itemKey(item))"
            :busy="itemBusyKey === itemKey(item)"
            @toggle="toggleSelected"
            @refresh="refreshItem"
            @edit="openIdentify"
          />
        </div>
        <VEmptyState v-else-if="!loading" icon="mdi-download-box-outline" title="暂无 qB 任务" />
        <VProgressLinear v-if="loading" indeterminate color="primary" />
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
          :testing-task-id="rssTestingTaskId"
          :running-task-id="rssRunningTaskId"
          :rss-enabled="rssEnabled"
          :controlling="rssControlLoading"
          @save="saveRssTasks"
          @reload="loadActive"
          @test="testRssTask"
          @run="runRssTask"
          @control="controlRss"
        />
        <VDataTable
          v-else-if="vtTab === 'rss_history'"
          :headers="rssHistoryHeaders"
          :items="rows"
          :loading="loading"
          density="compact"
          item-value="id"
          :items-per-page="-1"
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
          :items-per-page="-1"
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
          :items-per-page="-1"
          hide-default-footer
          class="data-table"
          no-data-text="暂无后台任务"
        />
      </section>
    </main>

    <ManualIdentifyDialog
      v-model="identifyDialog"
      :item="identifyItem"
      :categories="categoryOptions"
      :loading="Boolean(itemBusyKey)"
      @save="saveManualIdentify"
    />

    <VDialog v-model="rssTestDialog" max-width="1280">
      <VCard>
        <VCardTitle class="rss-test-title">
          <VIcon icon="mdi-rss" color="primary" />
          <span>{{ rssTestResult?.task?.name || 'RSS 测试结果' }}</span>
          <VSpacer />
          <VBtn
            icon="mdi-close"
            variant="text"
            aria-label="关闭"
            @click="rssTestDialog = false"
          />
        </VCardTitle>
        <VDivider />
        <VCardText v-if="rssTestResult" class="rss-test-content">
          <div class="rss-test-summary">
            <VChip size="small" variant="tonal">
              {{ rssTestResult.feed?.type?.toUpperCase() || 'RSS' }}
            </VChip>
            <VChip size="small" variant="tonal">
              共 {{ rssTestResult.counts?.total || 0 }} 条
            </VChip>
            <VChip size="small" color="success" variant="tonal">
              可处理 {{ rssTestResult.counts?.ready || 0 }}
            </VChip>
            <VChip size="small" variant="tonal">
              已过滤 {{ rssTestResult.counts?.filtered || 0 }}
            </VChip>
            <VChip size="small" color="warning" variant="tonal">
              缺少种子链接 {{ rssTestResult.counts?.missing_enclosure || 0 }}
            </VChip>
            <VChip size="small" color="info" variant="tonal">
              重复 {{ rssTestResult.counts?.duplicate || 0 }}
            </VChip>
            <VChip v-if="rssTestResult.truncated" size="small" color="warning" variant="tonal">
              仅显示前 {{ rssTestResult.items?.length || 0 }} 条
            </VChip>
          </div>
          <div v-if="rssTestResult.feed?.title" class="rss-feed-title">
            {{ rssTestResult.feed.title }}
          </div>
          <code class="rss-feed-url">{{ rssTestResult.feed?.final_url_masked }}</code>
          <VDataTable
            :headers="rssTestHeaders"
            :items="rssTestResult.items || []"
            density="compact"
            item-value="row_key"
            :items-per-page="-1"
            hide-default-footer
            class="data-table rss-test-table"
            no-data-text="RSS 中没有可解析条目"
          >
            <template #item.status="{ item }">
              <VChip :color="rssTestColor(item.status)" size="small" variant="tonal">
                {{ rssTestLabels[item.status] || item.status }}
              </VChip>
            </template>
            <template #item.enclosure_url_masked="{ item }">
              <code class="url-cell">{{ item.enclosure_url_masked || '-' }}</code>
            </template>
            <template #item.detail_url_masked="{ item }">
              <code class="url-cell">{{ item.detail_url_masked || '-' }}</code>
            </template>
          </VDataTable>
        </VCardText>
      </VCard>
    </VDialog>
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

.rss-test-title,
.rss-test-summary {
  display: flex;
  align-items: center;
}

.rss-test-title {
  min-height: 56px;
  gap: 10px;
}

.rss-test-title span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rss-test-content {
  display: grid;
  gap: 10px;
}

.rss-test-summary {
  flex-wrap: wrap;
  gap: 8px;
}

.rss-feed-title {
  font-weight: 600;
}

.rss-feed-url,
.url-cell {
  overflow-wrap: anywhere;
  white-space: normal;
}

.rss-test-table {
  max-height: min(65vh, 720px);
  overflow: auto;
}

.qb-task-line,
.progress-cell,
.media-cell,
.resource-cell {
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

.resource-cell {
  flex-direction: column;
  gap: 5px;
  line-height: 1.35;
}

.resource-token-line {
  overflow-wrap: anywhere;
}

.customization-line {
  overflow-wrap: anywhere;
  color: rgb(var(--v-theme-primary));
}

.customization-line strong {
  margin-right: 5px;
  font-weight: 600;
}

.resource-meta-line {
  display: flex;
  min-height: 20px;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.recognition-tooltip {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-block: 4px;
}

.recognition-tooltip code {
  white-space: normal;
  overflow-wrap: anywhere;
}

.filter-control {
  flex: 0 1 190px;
  min-width: 150px;
}
.rss-task-filter {
  flex: 1 1 320px;
  min-width: 240px;
  max-width: 520px;
}

.section-count {
  margin-bottom: 10px;
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 0.8rem;
}

.selection-bar {
  display: flex;
  min-height: 38px;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 0.8rem;
}

.selection-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.poster-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 20px;
  align-items: start;
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
  .rss-task-filter {
    flex: 1 1 100%;
    max-width: none;
  }

  .poster-grid {
    grid-template-columns: repeat(auto-fill, minmax(165px, 1fr));
    gap: 12px;
  }
}
</style>
