import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,mergeProps:_mergeProps,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,withKeys:_withKeys} = await importShared('vue');


const _hoisted_1 = { class: "app-page" };
const _hoisted_2 = { class: "title-block" };
const _hoisted_3 = { class: "text-caption text-medium-emphasis" };
const _hoisted_4 = { class: "workspace" };
const _hoisted_5 = {
  key: 0,
  class: "overview-section"
};
const _hoisted_6 = { class: "metric-grid" };
const _hoisted_7 = { key: 1 };
const _hoisted_8 = { class: "filter-bar" };
const _hoisted_9 = { class: "text-caption text-medium-emphasis" };
const _hoisted_10 = { key: 2 };
const _hoisted_11 = { class: "qb-toolbar" };
const _hoisted_12 = { class: "text-caption text-medium-emphasis" };
const _hoisted_13 = { class: "qb-task-line" };
const _hoisted_14 = {
  key: 1,
  class: "text-caption mt-1 text-truncate"
};
const _hoisted_15 = { class: "media-cell" };
const _hoisted_16 = {
  key: 0,
  class: "text-caption text-medium-emphasis"
};
const _hoisted_17 = { class: "progress-cell" };
const _hoisted_18 = { key: 3 };
const _hoisted_19 = { key: 4 };
const _hoisted_20 = { class: "section-count" };

const {computed,onBeforeUnmount,onMounted,ref,watch} = await importShared('vue');



const _sfc_main = {
  __name: 'AppPage',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
},
  setup(__props) {

const props = __props;

const activeTab = ref('overview');
const vtTab = ref('rss_tasks');
const loading = ref(false);
const errorMessage = ref('');
const overview = ref({ plugin: {}, counts: {}, capabilities: {} });
const rows = ref([]);
const total = ref(0);
const mediaState = ref('');
const mediaType = ref('');
const qbDownloaders = ref([]);
const qbDownloader = ref('');
const qbView = ref('');
const qbKeyword = ref('');
const qbTask = ref(null);
let qbPollTimer = null;

const tabs = [
  { title: '总览', value: 'overview', icon: 'mdi-view-dashboard-outline' },
  { title: '入库管理', value: 'library', icon: 'mdi-database-import-outline' },
  { title: 'QB 管理', value: 'qb', icon: 'mdi-download-box-outline' },
  { title: 'VT+', value: 'vt', icon: 'mdi-rss-box' },
  { title: '后台任务', value: 'tasks', icon: 'mdi-progress-clock' },
];

const mediaHeaders = [
  { title: '标题', key: 'title', minWidth: 190 },
  { title: '状态', key: 'state', width: 120 },
  { title: '类型', key: 'media_type', width: 100 },
  { title: 'TMDB', key: 'tmdb_id', width: 100 },
  { title: '季', key: 'season', width: 70 },
  { title: '分类', key: 'category', width: 120 },
  { title: '更新时间', key: 'updated_at', minWidth: 170 },
];

const torrentHeaders = [
  { title: '识别结果', key: 'media_title', minWidth: 210 },
  { title: '源名称', key: 'name', minWidth: 250 },
  { title: '库存', key: 'inventory_state', width: 110 },
  { title: '识别', key: 'recognition_state', width: 110 },
  { title: '下载状态', key: 'state', width: 120 },
  { title: '进度', key: 'progress', width: 100 },
  { title: '节点', key: 'downloader_id', width: 130 },
  { title: '分类', key: 'category', width: 110 },
  { title: '目标路径', key: 'target_name', minWidth: 250 },
  { title: 'Hash', key: 'info_hash', width: 120 },
];

const rssTaskHeaders = [
  { title: '任务', key: 'name', minWidth: 200 },
  { title: '启用', key: 'enabled', width: 80 },
  { title: '顺序', key: 'position', width: 80 },
  { title: '更新时间', key: 'updated_at', minWidth: 170 },
];

const rssHistoryHeaders = [
  { title: '标题', key: 'title', minWidth: 220 },
  { title: '任务', key: 'task_id', width: 150 },
  { title: '状态', key: 'status', width: 120 },
  { title: '原因', key: 'reason', minWidth: 220 },
  { title: '时间', key: 'updated_at', minWidth: 170 },
];

const taskHeaders = [
  { title: '任务类型', key: 'task_type', minWidth: 160 },
  { title: '状态', key: 'state', width: 110 },
  { title: '当前项目', key: 'current_item', minWidth: 180 },
  { title: '进度', key: 'progress_text', width: 120 },
  { title: '更新时间', key: 'updated_at', minWidth: 170 },
];

const capabilityRows = computed(() => Object.entries(
  overview.value.capabilities || {},
).map(([name, value]) => ({
  name,
  ready: Boolean(value?.ready),
  phase: value?.phase || value?.mode || '-',
})));

const qbRefreshing = computed(() => ['queued', 'running'].includes(qbTask.value?.state));
const qbProgress = computed(() => {
  const processed = Number(qbTask.value?.processed || 0);
  const taskTotal = Number(qbTask.value?.total || 0);
  return taskTotal > 0 ? Math.round((processed / taskTotal) * 100) : 0
});

const inventoryLabels = {
  exists: '已存在',
  partial: '不完整',
  missing: '不存在',
  unconfigured: '未配置',
  unavailable: '不可访问',
  unknown: '未知',
};

const recognitionLabels = {
  identified: '已识别',
  unidentified: '未识别',
  error: '失败',
  pending: '待识别',
};

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
  const response = unwrap(await props.api.get('plugin/RssAllInOne/overview'));
  overview.value = response || overview.value;
  if (response?.qb_task?.id && !qbTask.value?.id) {
    qbTask.value = response.qb_task;
    scheduleQbPoll(response.qb_task.id);
  }
}

async function loadQbDownloaders() {
  const response = unwrap(
    await props.api.get('plugin/RssAllInOne/qb/downloaders'),
  );
  qbDownloaders.value = (response?.items || []).map(item => ({
    title: `${item.name}${item.default ? ' · 默认' : ''}${item.ready ? '' : ' · 未就绪'}`,
    value: item.name,
    disabled: !item.ready,
  }));
}

async function loadActive() {
  loading.value = true;
  errorMessage.value = '';
  try {
    await loadOverview();
    if (activeTab.value === 'overview') {
      rows.value = [];
      total.value = 0;
      return
    }

    let path = '';
    let params = { offset: 0, limit: 100 };
    if (activeTab.value === 'library') {
      path = 'media';
      params = {
        ...params,
        state: mediaState.value,
        media_type: mediaType.value,
      };
    } else if (activeTab.value === 'qb') {
      path = 'torrents';
      params = {
        ...params,
        downloader_id: qbDownloader.value,
        view: qbView.value,
        keyword: qbKeyword.value.trim(),
      };
    } else if (activeTab.value === 'tasks') {
      path = 'tasks';
    } else if (activeTab.value === 'vt' && vtTab.value === 'rss_tasks') {
      path = 'rss/tasks';
    } else if (activeTab.value === 'vt' && vtTab.value === 'rss_history') {
      path = 'rss/history';
    }

    if (!path) {
      rows.value = [];
      total.value = 0;
      return
    }
    const response = unwrap(
      await props.api.get(`plugin/RssAllInOne/${path}`, { params }),
    );
    const items = response?.items || [];
    if (activeTab.value === 'tasks') {
      rows.value = normalizeTaskRows(items);
    } else if (activeTab.value === 'qb') {
      rows.value = items.map(item => ({
        ...item,
        row_key: `${item.downloader_id}:${item.info_hash}`,
        target_name: item.details?.inventory_plan?.target_name || '',
      }));
    } else {
      rows.value = items;
    }
    total.value = Number(response?.total || 0);
  } catch (error) {
    errorMessage.value = error?.message || '数据加载失败';
    rows.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

function scheduleQbPoll(taskId) {
  if (!taskId) return
  window.clearTimeout(qbPollTimer);
  qbPollTimer = window.setTimeout(() => pollQbTask(taskId), 1200);
}

async function pollQbTask(taskId) {
  try {
    const response = unwrap(
      await props.api.get(`plugin/RssAllInOne/tasks/${taskId}`),
    );
    if (!response?.success || !response?.task) return
    qbTask.value = response.task;
    if (['queued', 'running'].includes(response.task.state)) {
      scheduleQbPoll(taskId);
    } else {
      await loadActive();
    }
  } catch (error) {
    errorMessage.value = error?.message || '读取 QB 刷新进度失败';
  }
}

async function refreshQb() {
  errorMessage.value = '';
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/qb/refresh', {
        force_recognition: false,
      }),
    );
    if (!response?.success && !response?.task_id) {
      errorMessage.value = response?.message || 'QB 刷新启动失败';
      return
    }
    qbTask.value = {
      id: response.task_id,
      state: 'running',
      processed: 0,
      total: 0,
      current_item: '',
    };
    scheduleQbPoll(response.task_id);
  } catch (error) {
    errorMessage.value = error?.message || 'QB 刷新启动失败';
  }
}

function inventoryColor(state) {
  return {
    exists: 'success',
    partial: 'warning',
    missing: 'info',
    unavailable: 'error',
    unconfigured: 'warning',
  }[state] || 'default'
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
      await loadQbDownloaders();
    } catch (error) {
      errorMessage.value = error?.message || '读取 qB 节点失败';
    }
  }
  await loadActive();
});
watch(vtTab, () => {
  if (activeTab.value === 'vt') loadActive();
});
watch([mediaState, mediaType], () => {
  if (activeTab.value === 'library') loadActive();
});
watch([qbDownloader, qbView], () => {
  if (activeTab.value === 'qb') loadActive();
});
onMounted(loadActive);
onBeforeUnmount(() => window.clearTimeout(qbPollTimer));

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VChip = _resolveComponent("VChip");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VTooltip = _resolveComponent("VTooltip");
  const _component_VToolbar = _resolveComponent("VToolbar");
  const _component_VTab = _resolveComponent("VTab");
  const _component_VTabs = _resolveComponent("VTabs");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VSheet = _resolveComponent("VSheet");
  const _component_VTable = _resolveComponent("VTable");
  const _component_VSelect = _resolveComponent("VSelect");
  const _component_VDataTable = _resolveComponent("VDataTable");
  const _component_VBtnToggle = _resolveComponent("VBtnToggle");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VProgressLinear = _resolveComponent("VProgressLinear");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      density: "comfortable",
      color: "surface",
      class: "topbar"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VIcon, {
          icon: "mdi-rss",
          color: "primary",
          class: "ms-3 me-3"
        }),
        _createElementVNode("div", _hoisted_2, [
          _cache[7] || (_cache[7] = _createElementVNode("div", { class: "text-h6" }, "RSS一条龙", -1)),
          _createElementVNode("div", _hoisted_3, _toDisplayString(overview.value.plugin?.enabled ? '运行已启用' : '运行未启用'), 1)
        ]),
        _createVNode(_component_VSpacer),
        _createVNode(_component_VChip, {
          color: "info",
          variant: "tonal",
          size: "small",
          class: "me-2"
        }, {
          default: _withCtx(() => [
            _createTextVNode("v" + _toDisplayString(overview.value.plugin?.version || '0.2.0'), 1)
          ]),
          _: 1
        }),
        _createVNode(_component_VTooltip, { text: "刷新" }, {
          activator: _withCtx(({ props: tooltipProps }) => [
            _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
              icon: "mdi-refresh",
              variant: "text",
              loading: loading.value,
              "aria-label": "刷新",
              onClick: loadActive
            }), null, 16, ["loading"])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VTabs, {
      modelValue: activeTab.value,
      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((activeTab).value = $event)),
      color: "primary",
      density: "compact",
      "show-arrows": "",
      class: "main-tabs"
    }, {
      default: _withCtx(() => [
        (_openBlock(), _createElementBlock(_Fragment, null, _renderList(tabs, (tab) => {
          return _createVNode(_component_VTab, {
            key: tab.value,
            value: tab.value
          }, {
            default: _withCtx(() => [
              _createVNode(_component_VIcon, {
                icon: tab.icon,
                size: "18",
                class: "me-2"
              }, null, 8, ["icon"]),
              _createTextVNode(" " + _toDisplayString(tab.title), 1)
            ]),
            _: 2
          }, 1032, ["value"])
        }), 64))
      ]),
      _: 1
    }, 8, ["modelValue"]),
    (errorMessage.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 0,
          type: "error",
          variant: "tonal",
          class: "status-alert"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(errorMessage.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    _createElementVNode("main", _hoisted_4, [
      (activeTab.value === 'overview')
        ? (_openBlock(), _createElementBlock("section", _hoisted_5, [
            _createElementVNode("div", _hoisted_6, [
              _createVNode(_component_VSheet, {
                border: "",
                class: "metric-item"
              }, {
                default: _withCtx(() => [
                  _cache[8] || (_cache[8] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "媒体记录", -1)),
                  _createElementVNode("strong", null, _toDisplayString(overview.value.counts?.media || 0), 1)
                ]),
                _: 1
              }),
              _createVNode(_component_VSheet, {
                border: "",
                class: "metric-item"
              }, {
                default: _withCtx(() => [
                  _cache[9] || (_cache[9] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "qB 快照", -1)),
                  _createElementVNode("strong", null, _toDisplayString(overview.value.counts?.torrents || 0), 1)
                ]),
                _: 1
              }),
              _createVNode(_component_VSheet, {
                border: "",
                class: "metric-item"
              }, {
                default: _withCtx(() => [
                  _cache[10] || (_cache[10] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "RSS 历史", -1)),
                  _createElementVNode("strong", null, _toDisplayString(overview.value.counts?.rss_history || 0), 1)
                ]),
                _: 1
              }),
              _createVNode(_component_VSheet, {
                border: "",
                class: "metric-item"
              }, {
                default: _withCtx(() => [
                  _cache[11] || (_cache[11] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "后台任务", -1)),
                  _createElementVNode("strong", null, _toDisplayString(overview.value.counts?.background_tasks || 0), 1)
                ]),
                _: 1
              })
            ]),
            _createVNode(_component_VTable, {
              density: "compact",
              class: "capability-table"
            }, {
              default: _withCtx(() => [
                _cache[12] || (_cache[12] = _createElementVNode("thead", null, [
                  _createElementVNode("tr", null, [
                    _createElementVNode("th", null, "能力"),
                    _createElementVNode("th", null, "状态"),
                    _createElementVNode("th", null, "阶段")
                  ])
                ], -1)),
                _createElementVNode("tbody", null, [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(capabilityRows.value, (item) => {
                    return (_openBlock(), _createElementBlock("tr", {
                      key: item.name
                    }, [
                      _createElementVNode("td", null, _toDisplayString(item.name), 1),
                      _createElementVNode("td", null, [
                        _createVNode(_component_VChip, {
                          color: item.ready ? 'success' : 'warning',
                          size: "small",
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(item.ready ? '就绪' : '待接入'), 1)
                          ]),
                          _: 2
                        }, 1032, ["color"])
                      ]),
                      _createElementVNode("td", null, _toDisplayString(item.phase), 1)
                    ]))
                  }), 128))
                ])
              ]),
              _: 1
            })
          ]))
        : (activeTab.value === 'library')
          ? (_openBlock(), _createElementBlock("section", _hoisted_7, [
              _createElementVNode("div", _hoisted_8, [
                _createVNode(_component_VSelect, {
                  modelValue: mediaState.value,
                  "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((mediaState).value = $event)),
                  items: [
              { title: '全部状态', value: '' },
              { title: '已发现', value: 'discovered' },
              { title: '已识别', value: 'identified' },
              { title: '未识别', value: 'unidentified' },
              { title: '已存在', value: 'existing' },
              { title: '待入库', value: 'pending' },
              { title: '入库中', value: 'importing' },
              { title: '已入库', value: 'imported' },
            ],
                  label: "状态",
                  density: "compact",
                  "hide-details": "",
                  class: "filter-control"
                }, null, 8, ["modelValue"]),
                _createVNode(_component_VSelect, {
                  modelValue: mediaType.value,
                  "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((mediaType).value = $event)),
                  items: [
              { title: '全部类型', value: '' },
              { title: '电影', value: 'movie' },
              { title: '电视剧', value: 'tv' },
            ],
                  label: "类型",
                  density: "compact",
                  "hide-details": "",
                  class: "filter-control"
                }, null, 8, ["modelValue"]),
                _createElementVNode("span", _hoisted_9, _toDisplayString(total.value) + " 项", 1)
              ]),
              _createVNode(_component_VDataTable, {
                headers: mediaHeaders,
                items: rows.value,
                loading: loading.value,
                density: "compact",
                "item-value": "id",
                "hide-default-footer": "",
                class: "data-table",
                "no-data-text": "暂无媒体记录"
              }, null, 8, ["items", "loading"])
            ]))
          : (activeTab.value === 'qb')
            ? (_openBlock(), _createElementBlock("section", _hoisted_10, [
                _createElementVNode("div", _hoisted_11, [
                  _createVNode(_component_VSelect, {
                    modelValue: qbDownloader.value,
                    "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((qbDownloader).value = $event)),
                    items: [{ title: '全部节点', value: '' }, ...qbDownloaders.value],
                    label: "QB 节点",
                    density: "compact",
                    "hide-details": "",
                    class: "filter-control"
                  }, null, 8, ["modelValue", "items"]),
                  _createVNode(_component_VBtnToggle, {
                    modelValue: qbView.value,
                    "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((qbView).value = $event)),
                    mandatory: "",
                    divided: "",
                    density: "compact",
                    variant: "outlined",
                    color: "primary"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VBtn, { value: "" }, {
                        default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
                          _createTextVNode("全部", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VBtn, { value: "existing" }, {
                        default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
                          _createTextVNode("已存在", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VBtn, { value: "pending" }, {
                        default: _withCtx(() => [...(_cache[15] || (_cache[15] = [
                          _createTextVNode("待下载", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }, 8, ["modelValue"]),
                  _createVNode(_component_VTextField, {
                    modelValue: qbKeyword.value,
                    "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((qbKeyword).value = $event)),
                    label: "搜索名称或 Hash",
                    "prepend-inner-icon": "mdi-magnify",
                    density: "compact",
                    "hide-details": "",
                    clearable: "",
                    class: "qb-search",
                    onKeyup: _withKeys(loadActive, ["enter"]),
                    "onClick:clear": loadActive
                  }, null, 8, ["modelValue"]),
                  _createVNode(_component_VSpacer),
                  _createElementVNode("span", _hoisted_12, _toDisplayString(total.value) + " 项", 1),
                  _createVNode(_component_VBtn, {
                    color: "primary",
                    variant: "tonal",
                    "prepend-icon": "mdi-refresh",
                    loading: qbRefreshing.value,
                    disabled: qbRefreshing.value || !overview.value.plugin?.enabled,
                    onClick: refreshQb
                  }, {
                    default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                      _createTextVNode(" 刷新识别 ", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading", "disabled"])
                ]),
                (qbTask.value)
                  ? (_openBlock(), _createBlock(_component_VAlert, {
                      key: 0,
                      type: qbTask.value.state === 'failed' ? 'error' : 'info',
                      variant: "tonal",
                      density: "compact",
                      class: "qb-task-status"
                    }, {
                      default: _withCtx(() => [
                        _createElementVNode("div", _hoisted_13, [
                          _createElementVNode("span", null, _toDisplayString(qbRefreshing.value ? '正在读取 QB、识别并核对本地库存' : `任务状态：${qbTask.value.state}`), 1),
                          _createElementVNode("span", null, _toDisplayString(qbTask.value.processed || 0) + "/" + _toDisplayString(qbTask.value.total || 0), 1)
                        ]),
                        (qbRefreshing.value)
                          ? (_openBlock(), _createBlock(_component_VProgressLinear, {
                              key: 0,
                              "model-value": qbProgress.value,
                              height: "4",
                              class: "mt-2"
                            }, null, 8, ["model-value"]))
                          : _createCommentVNode("", true),
                        (qbTask.value.current_item)
                          ? (_openBlock(), _createElementBlock("div", _hoisted_14, _toDisplayString(qbTask.value.current_item), 1))
                          : _createCommentVNode("", true)
                      ]),
                      _: 1
                    }, 8, ["type"]))
                  : _createCommentVNode("", true),
                _createVNode(_component_VDataTable, {
                  headers: torrentHeaders,
                  items: rows.value,
                  loading: loading.value,
                  density: "compact",
                  "item-value": "row_key",
                  "hide-default-footer": "",
                  class: "data-table",
                  "no-data-text": "暂无 qB 任务快照"
                }, {
                  "item.media_title": _withCtx(({ item }) => [
                    _createElementVNode("div", _hoisted_15, [
                      _createElementVNode("strong", null, _toDisplayString(item.media_title || '未识别'), 1),
                      (item.media_year || item.season !== null)
                        ? (_openBlock(), _createElementBlock("span", _hoisted_16, _toDisplayString(item.media_year || '') + _toDisplayString(item.season !== null && item.season !== undefined ? ` · S${String(item.season).padStart(2, '0')}` : ''), 1))
                        : _createCommentVNode("", true)
                    ])
                  ]),
                  "item.inventory_state": _withCtx(({ item }) => [
                    _createVNode(_component_VChip, {
                      color: inventoryColor(item.inventory_state),
                      size: "small",
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(inventoryLabels[item.inventory_state] || item.inventory_state), 1)
                      ]),
                      _: 2
                    }, 1032, ["color"])
                  ]),
                  "item.recognition_state": _withCtx(({ item }) => [
                    _createVNode(_component_VChip, {
                      color: recognitionColor(item.recognition_state),
                      size: "small",
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(recognitionLabels[item.recognition_state] || item.recognition_state), 1)
                      ]),
                      _: 2
                    }, 1032, ["color"])
                  ]),
                  "item.progress": _withCtx(({ item }) => [
                    _createElementVNode("div", _hoisted_17, [
                      _createVNode(_component_VProgressLinear, {
                        "model-value": Number(item.progress || 0),
                        height: "5"
                      }, null, 8, ["model-value"]),
                      _createElementVNode("span", null, _toDisplayString(Math.round(Number(item.progress || 0))) + "%", 1)
                    ])
                  ]),
                  "item.info_hash": _withCtx(({ item }) => [
                    _createElementVNode("code", null, _toDisplayString(String(item.info_hash || '').slice(0, 10)), 1)
                  ]),
                  _: 1
                }, 8, ["items", "loading"])
              ]))
            : (activeTab.value === 'vt')
              ? (_openBlock(), _createElementBlock("section", _hoisted_18, [
                  _createVNode(_component_VTabs, {
                    modelValue: vtTab.value,
                    "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((vtTab).value = $event)),
                    density: "compact",
                    color: "primary",
                    class: "sub-tabs"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VTab, { value: "rss_tasks" }, {
                        default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
                          _createTextVNode("RSS任务", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VTab, { value: "rss_history" }, {
                        default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
                          _createTextVNode("RSS历史", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VTab, { value: "sites" }, {
                        default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
                          _createTextVNode("站点身份", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }, 8, ["modelValue"]),
                  (vtTab.value === 'rss_tasks')
                    ? (_openBlock(), _createBlock(_component_VDataTable, {
                        key: 0,
                        headers: rssTaskHeaders,
                        items: rows.value,
                        loading: loading.value,
                        density: "compact",
                        "item-value": "id",
                        "hide-default-footer": "",
                        class: "data-table",
                        "no-data-text": "暂无 RSS 任务"
                      }, null, 8, ["items", "loading"]))
                    : (vtTab.value === 'rss_history')
                      ? (_openBlock(), _createBlock(_component_VDataTable, {
                          key: 1,
                          headers: rssHistoryHeaders,
                          items: rows.value,
                          loading: loading.value,
                          density: "compact",
                          "item-value": "id",
                          "hide-default-footer": "",
                          class: "data-table",
                          "no-data-text": "暂无 RSS 历史"
                        }, null, 8, ["items", "loading"]))
                      : (_openBlock(), _createBlock(_component_VTable, {
                          key: 2,
                          density: "compact",
                          class: "capability-table"
                        }, {
                          default: _withCtx(() => [
                            _cache[23] || (_cache[23] = _createElementVNode("thead", null, [
                              _createElementVNode("tr", null, [
                                _createElementVNode("th", null, "来源"),
                                _createElementVNode("th", null, "模式"),
                                _createElementVNode("th", null, "状态")
                              ])
                            ], -1)),
                            _createElementVNode("tbody", null, [
                              _createElementVNode("tr", null, [
                                _cache[21] || (_cache[21] = _createElementVNode("td", null, "当前 MoviePilot", -1)),
                                _cache[22] || (_cache[22] = _createElementVNode("td", null, "站点服务", -1)),
                                _createElementVNode("td", null, [
                                  _createVNode(_component_VChip, {
                                    size: "small",
                                    variant: "tonal",
                                    color: "warning"
                                  }, {
                                    default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                                      _createTextVNode("适配器待接入", -1)
                                    ]))]),
                                    _: 1
                                  })
                                ])
                              ])
                            ])
                          ]),
                          _: 1
                        }))
                ]))
              : (activeTab.value === 'tasks')
                ? (_openBlock(), _createElementBlock("section", _hoisted_19, [
                    _createElementVNode("div", _hoisted_20, _toDisplayString(total.value) + " 个后台任务", 1),
                    _createVNode(_component_VDataTable, {
                      headers: taskHeaders,
                      items: rows.value,
                      loading: loading.value,
                      density: "compact",
                      "item-value": "id",
                      "hide-default-footer": "",
                      class: "data-table",
                      "no-data-text": "暂无后台任务"
                    }, null, 8, ["items", "loading"])
                  ]))
                : _createCommentVNode("", true)
    ])
  ]))
}
}

};
const AppPage = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-e2b35360"]]);

export { AppPage as default };
