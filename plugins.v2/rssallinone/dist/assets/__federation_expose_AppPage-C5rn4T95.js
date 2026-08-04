import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {toDisplayString:_toDisplayString$1,createElementVNode:_createElementVNode$1,resolveComponent:_resolveComponent$1,createVNode:_createVNode$1,mergeProps:_mergeProps$1,withCtx:_withCtx$1,createTextVNode:_createTextVNode$1,openBlock:_openBlock$1,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode$1,renderList:_renderList$1,Fragment:_Fragment$1,createElementBlock:_createElementBlock$1,withModifiers:_withModifiers} = await importShared('vue');


const _hoisted_1$1 = { class: "rss-editor" };
const _hoisted_2$1 = { class: "rss-toolbar" };
const _hoisted_3$1 = { class: "text-caption text-medium-emphasis" };
const _hoisted_4$1 = { class: "task-title" };
const _hoisted_5$1 = { class: "switch-grid" };

const {computed: computed$1,ref: ref$1,watch: watch$1} = await importShared('vue');



const _sfc_main$1 = {
  __name: 'RssTaskEditor',
  props: {
  items: { type: Array, default: () => [] },
  downloaders: { type: Array, default: () => [] },
  sites: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  testingTaskId: { type: String, default: '' },
},
  emits: ['save', 'reload', 'test'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const tasks = ref$1([]);
const expanded = ref$1([]);

const booleanOptions = [
  { key: 'pause_on_add', label: '添加种子时暂停' },
  { key: 'push_torrent_file', label: '推送种子文件' },
  { key: 'recognize_cn', label: '识别国语' },
  { key: 'recognize_fx', label: '识别特效' },
  { key: 'add_chinese_title', label: '添加中文标题' },
  { key: 'import_enabled', label: '入库' },
  { key: 'rename_enabled', label: '重命名' },
  { key: 'download_enabled', label: '下载' },
  { key: 'delete_files', label: '删除文件' },
];

const downloaderOptions = computed$1(() => props.downloaders.map(item => ({
  title: `${item.name}${item.default ? ' · 默认' : ''}${item.ready ? '' : ' · 未就绪'}`,
  value: item.name,
  disabled: !item.enabled,
})));

const siteOptions = computed$1(() => [
  { title: '不使用站点标签识别', value: '' },
  ...props.sites.map(item => ({
    title: `${item.name || item.domain}${item.enabled ? '' : ' · 未启用'}`,
    value: String(item.id || ''),
  })),
]);

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function newId() {
  return globalThis.crypto?.randomUUID?.().replaceAll('-', '')
    || `rss-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function defaultConfig() {
  return {
    rss_url: '',
    qb_downloader: '',
    rss_cron: '*/10 * * * *',
    save_path: '',
    qb_category: '',
    name_contains: '',
    start_cron: '*/5 * * * *',
    fallback_cron: '*/10 * * * *',
    delete_after_minutes: 0,
    upload_limit_kbps: 0,
    path_mappings: '',
    rename_rules: '',
    site_id: '',
    cn_keywords: '国语,国配',
    pause_on_add: true,
    push_torrent_file: false,
    recognize_cn: false,
    recognize_fx: false,
    add_chinese_title: false,
    import_enabled: true,
    rename_enabled: false,
    download_enabled: true,
    delete_files: false,
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
  const task = normalizeTask({}, tasks.value.length);
  tasks.value.push(task);
  expanded.value = [...expanded.value, task.id];
}

function removeTask(index) {
  const [removed] = tasks.value.splice(index, 1);
  expanded.value = expanded.value.filter(id => id !== removed?.id);
  tasks.value.forEach((task, position) => { task.position = position; });
}

function saveTasks() {
  emit('save', tasks.value.map((task, position) => ({
    ...clone(task),
    position,
  })));
}

function testTask(task, position) {
  emit('test', {
    ...clone(task),
    position,
  });
}

watch$1(
  () => props.items,
  value => {
    tasks.value = (value || []).map(normalizeTask);
    expanded.value = tasks.value.length === 1 ? [tasks.value[0].id] : [];
  },
  { immediate: true, deep: true },
);

return (_ctx, _cache) => {
  const _component_VSpacer = _resolveComponent$1("VSpacer");
  const _component_VBtn = _resolveComponent$1("VBtn");
  const _component_VTooltip = _resolveComponent$1("VTooltip");
  const _component_VAlert = _resolveComponent$1("VAlert");
  const _component_VSwitch = _resolveComponent$1("VSwitch");
  const _component_VChip = _resolveComponent$1("VChip");
  const _component_VExpansionPanelTitle = _resolveComponent$1("VExpansionPanelTitle");
  const _component_VTextField = _resolveComponent$1("VTextField");
  const _component_VCol = _resolveComponent$1("VCol");
  const _component_VSelect = _resolveComponent$1("VSelect");
  const _component_VTextarea = _resolveComponent$1("VTextarea");
  const _component_VRow = _resolveComponent$1("VRow");
  const _component_VDivider = _resolveComponent$1("VDivider");
  const _component_VExpansionPanelText = _resolveComponent$1("VExpansionPanelText");
  const _component_VExpansionPanel = _resolveComponent$1("VExpansionPanel");
  const _component_VExpansionPanels = _resolveComponent$1("VExpansionPanels");

  return (_openBlock$1(), _createElementBlock$1("div", _hoisted_1$1, [
    _createElementVNode$1("div", _hoisted_2$1, [
      _createElementVNode$1("span", _hoisted_3$1, _toDisplayString$1(tasks.value.length) + " 条任务", 1),
      _createVNode$1(_component_VSpacer),
      _createVNode$1(_component_VTooltip, { text: "重新读取" }, {
        activator: _withCtx$1(({ props: tooltipProps }) => [
          _createVNode$1(_component_VBtn, _mergeProps$1(tooltipProps, {
            icon: "mdi-refresh",
            variant: "text",
            loading: __props.loading,
            "aria-label": "重新读取",
            onClick: _cache[0] || (_cache[0] = $event => (emit('reload')))
          }), null, 16, ["loading"])
        ]),
        _: 1
      }),
      _createVNode$1(_component_VBtn, {
        "prepend-icon": "mdi-plus",
        variant: "text",
        onClick: addTask
      }, {
        default: _withCtx$1(() => [...(_cache[3] || (_cache[3] = [
          _createTextVNode$1(" 添加任务 ", -1)
        ]))]),
        _: 1
      }),
      _createVNode$1(_component_VBtn, {
        "prepend-icon": "mdi-content-save",
        color: "primary",
        variant: "tonal",
        loading: __props.loading,
        onClick: saveTasks
      }, {
        default: _withCtx$1(() => [...(_cache[4] || (_cache[4] = [
          _createTextVNode$1(" 保存 ", -1)
        ]))]),
        _: 1
      }, 8, ["loading"])
    ]),
    (tasks.value.length === 0)
      ? (_openBlock$1(), _createBlock$1(_component_VAlert, {
          key: 0,
          type: "info",
          variant: "tonal"
        }, {
          default: _withCtx$1(() => [...(_cache[5] || (_cache[5] = [
            _createTextVNode$1(" 暂无 RSS 任务 ", -1)
          ]))]),
          _: 1
        }))
      : (_openBlock$1(), _createBlock$1(_component_VExpansionPanels, {
          key: 1,
          modelValue: expanded.value,
          "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((expanded).value = $event)),
          multiple: "",
          class: "task-panels"
        }, {
          default: _withCtx$1(() => [
            (_openBlock$1(true), _createElementBlock$1(_Fragment$1, null, _renderList$1(tasks.value, (task, index) => {
              return (_openBlock$1(), _createBlock$1(_component_VExpansionPanel, {
                key: task.id,
                value: task.id
              }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_VExpansionPanelTitle, null, {
                    default: _withCtx$1(() => [
                      _createElementVNode$1("div", _hoisted_4$1, [
                        _createVNode$1(_component_VSwitch, {
                          modelValue: task.enabled,
                          "onUpdate:modelValue": $event => ((task.enabled) = $event),
                          density: "compact",
                          "hide-details": "",
                          color: "primary",
                          onClick: _cache[1] || (_cache[1] = _withModifiers(() => {}, ["stop"]))
                        }, null, 8, ["modelValue", "onUpdate:modelValue"]),
                        _createElementVNode$1("strong", null, _toDisplayString$1(task.name || `RSS任务 ${index + 1}`), 1),
                        (task.config.qb_category)
                          ? (_openBlock$1(), _createBlock$1(_component_VChip, {
                              key: 0,
                              size: "small",
                              variant: "tonal"
                            }, {
                              default: _withCtx$1(() => [
                                _createTextVNode$1(_toDisplayString$1(task.config.qb_category), 1)
                              ]),
                              _: 2
                            }, 1024))
                          : _createCommentVNode$1("", true),
                        _createVNode$1(_component_VSpacer),
                        _createVNode$1(_component_VTooltip, { text: "测试 RSS" }, {
                          activator: _withCtx$1(({ props: tooltipProps }) => [
                            _createVNode$1(_component_VBtn, _mergeProps$1({ ref_for: true }, tooltipProps, {
                              icon: "mdi-flask-outline",
                              size: "small",
                              variant: "text",
                              color: "primary",
                              loading: __props.testingTaskId === task.id,
                              disabled: !String(task.config.rss_url || '').trim(),
                              "aria-label": "测试 RSS",
                              onClick: _withModifiers($event => (testTask(task, index)), ["stop"])
                            }), null, 16, ["loading", "disabled", "onClick"])
                          ]),
                          _: 2
                        }, 1024),
                        _createVNode$1(_component_VTooltip, { text: "删除任务" }, {
                          activator: _withCtx$1(({ props: tooltipProps }) => [
                            _createVNode$1(_component_VBtn, _mergeProps$1({ ref_for: true }, tooltipProps, {
                              icon: "mdi-delete-outline",
                              size: "small",
                              variant: "text",
                              color: "error",
                              "aria-label": "删除任务",
                              onClick: _withModifiers($event => (removeTask(index)), ["stop"])
                            }), null, 16, ["onClick"])
                          ]),
                          _: 2
                        }, 1024)
                      ])
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode$1(_component_VExpansionPanelText, null, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_VRow, { dense: "" }, {
                        default: _withCtx$1(() => [
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "4"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextField, {
                                modelValue: task.name,
                                "onUpdate:modelValue": $event => ((task.name) = $event),
                                label: "任务名称"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "8"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextField, {
                                modelValue: task.config.rss_url,
                                "onUpdate:modelValue": $event => ((task.config.rss_url) = $event),
                                label: "RSS URL"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "4"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VSelect, {
                                modelValue: task.config.qb_downloader,
                                "onUpdate:modelValue": $event => ((task.config.qb_downloader) = $event),
                                items: downloaderOptions.value,
                                label: "QB下载器"
                              }, null, 8, ["modelValue", "onUpdate:modelValue", "items"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "4"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextField, {
                                modelValue: task.config.qb_category,
                                "onUpdate:modelValue": $event => ((task.config.qb_category) = $event),
                                label: "QB分类"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "4"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextField, {
                                modelValue: task.config.save_path,
                                "onUpdate:modelValue": $event => ((task.config.save_path) = $event),
                                label: "保存路径"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "4"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextField, {
                                modelValue: task.config.rss_cron,
                                "onUpdate:modelValue": $event => ((task.config.rss_cron) = $event),
                                label: "RSS周期 (CRON)"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "4"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextField, {
                                modelValue: task.config.start_cron,
                                "onUpdate:modelValue": $event => ((task.config.start_cron) = $event),
                                label: "开始任务 CRON"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "4"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextField, {
                                modelValue: task.config.fallback_cron,
                                "onUpdate:modelValue": $event => ((task.config.fallback_cron) = $event),
                                label: "轮询兜底 CRON"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextField, {
                                modelValue: task.config.name_contains,
                                "onUpdate:modelValue": $event => ((task.config.name_contains) = $event),
                                label: "限制条件 (名称包含)"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "3"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextField, {
                                modelValue: task.config.delete_after_minutes,
                                "onUpdate:modelValue": $event => ((task.config.delete_after_minutes) = $event),
                                modelModifiers: { number: true },
                                label: "完成后删除任务 (分钟)",
                                type: "number",
                                min: "0"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "3"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextField, {
                                modelValue: task.config.upload_limit_kbps,
                                "onUpdate:modelValue": $event => ((task.config.upload_limit_kbps) = $event),
                                modelModifiers: { number: true },
                                label: "上传限速 (kb/s)",
                                type: "number",
                                min: "0"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextarea, {
                                modelValue: task.config.path_mappings,
                                "onUpdate:modelValue": $event => ((task.config.path_mappings) = $event),
                                label: "路径映射",
                                rows: "3",
                                "auto-grow": ""
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextarea, {
                                modelValue: task.config.rename_rules,
                                "onUpdate:modelValue": $event => ((task.config.rename_rules) = $event),
                                label: "重命名规则",
                                rows: "3",
                                "auto-grow": ""
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VSelect, {
                                modelValue: task.config.site_id,
                                "onUpdate:modelValue": $event => ((task.config.site_id) = $event),
                                items: siteOptions.value,
                                label: "站点访问身份"
                              }, null, 8, ["modelValue", "onUpdate:modelValue", "items"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$1(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$1(() => [
                              _createVNode$1(_component_VTextField, {
                                modelValue: task.config.cn_keywords,
                                "onUpdate:modelValue": $event => ((task.config.cn_keywords) = $event),
                                label: "国语关键词"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024)
                        ]),
                        _: 2
                      }, 1024),
                      _createVNode$1(_component_VDivider, { class: "mb-3" }),
                      _createElementVNode$1("div", _hoisted_5$1, [
                        (_openBlock$1(), _createElementBlock$1(_Fragment$1, null, _renderList$1(booleanOptions, (option) => {
                          return _createVNode$1(_component_VSwitch, {
                            key: option.key,
                            modelValue: task.config[option.key],
                            "onUpdate:modelValue": $event => ((task.config[option.key]) = $event),
                            label: option.label,
                            density: "compact",
                            color: "primary",
                            "hide-details": ""
                          }, null, 8, ["modelValue", "onUpdate:modelValue", "label"])
                        }), 64))
                      ])
                    ]),
                    _: 2
                  }, 1024)
                ]),
                _: 2
              }, 1032, ["value"]))
            }), 128))
          ]),
          _: 1
        }, 8, ["modelValue"]))
  ]))
}
}

};
const RssTaskEditor = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-198861f8"]]);

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
const _hoisted_17 = { class: "resource-cell" };
const _hoisted_18 = { class: "customization-line" };
const _hoisted_19 = {
  key: 0,
  class: "resource-token-line"
};
const _hoisted_20 = {
  key: 1,
  class: "text-caption text-medium-emphasis"
};
const _hoisted_21 = { class: "resource-meta-line" };
const _hoisted_22 = { class: "recognition-tooltip" };
const _hoisted_23 = {
  key: 1,
  class: "text-caption text-medium-emphasis"
};
const _hoisted_24 = { class: "progress-cell" };
const _hoisted_25 = { key: 3 };
const _hoisted_26 = { key: 4 };
const _hoisted_27 = { class: "section-count" };
const _hoisted_28 = { class: "rss-test-summary" };
const _hoisted_29 = {
  key: 0,
  class: "rss-feed-title"
};
const _hoisted_30 = { class: "rss-feed-url" };
const _hoisted_31 = { class: "url-cell" };
const _hoisted_32 = { class: "url-cell" };

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
const successMessage = ref('');
const overview = ref({ plugin: {}, counts: {}, capabilities: {} });
const rows = ref([]);
const total = ref(0);
const rssTasks = ref([]);
const allQbDownloaders = ref([]);
const siteIdentities = ref([]);
const mediaState = ref('');
const mediaType = ref('');
const qbDownloaders = ref([]);
const qbDownloader = ref('');
const qbView = ref('');
const qbKeyword = ref('');
const qbTask = ref(null);
const rssTestingTaskId = ref('');
const rssTestDialog = ref(false);
const rssTestResult = ref(null);
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
  { title: '资源信息', key: 'resource_info', minWidth: 280 },
  { title: '库存', key: 'inventory_state', width: 110 },
  { title: '识别', key: 'recognition_state', width: 110 },
  { title: '下载状态', key: 'state', width: 120 },
  { title: '进度', key: 'progress', width: 100 },
  { title: '节点', key: 'downloader_id', width: 130 },
  { title: '分类', key: 'category', width: 110 },
  { title: '库存路径', key: 'target_name', minWidth: 280 },
  { title: '硬链接路径', key: 'link_target', minWidth: 280 },
  { title: 'Hash', key: 'info_hash', width: 120 },
];

const rssHistoryHeaders = [
  { title: '标题', key: 'title', minWidth: 220 },
  { title: '任务', key: 'task_id', width: 150 },
  { title: '状态', key: 'status', width: 120 },
  { title: '原因', key: 'reason', minWidth: 220 },
  { title: '时间', key: 'updated_at', minWidth: 170 },
];

const rssTestHeaders = [
  { title: '状态', key: 'status', width: 130 },
  { title: '标题', key: 'title', minWidth: 300 },
  { title: '种子 ID', key: 'torrent_id', width: 100 },
  { title: '发布时间', key: 'published', minWidth: 180 },
  { title: '种子链接', key: 'enclosure_url_masked', minWidth: 300 },
  { title: '详情链接', key: 'detail_url_masked', minWidth: 300 },
  { title: '原因', key: 'reason', minWidth: 220 },
];

const siteHeaders = [
  { title: '站点', key: 'name', minWidth: 180 },
  { title: '地址', key: 'domain', minWidth: 260 },
  { title: '认证方式', key: 'auth_mode', width: 120 },
  { title: '启用', key: 'enabled', width: 90 },
  { title: '状态', key: 'ready', width: 100 },
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
  empty: '空资源',
  ambiguous: '目录冲突',
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

const rssTestLabels = {
  ready: '可处理',
  filtered: '已过滤',
  missing_enclosure: '缺少种子链接',
  duplicate: '重复',
  invalid: '无效',
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

function uniqueTexts(values) {
  const result = [];
  for (const value of values || []) {
    const text = String(value || '').trim();
    if (text && !result.some(item => item.toLocaleLowerCase() === text.toLocaleLowerCase())) {
      result.push(text);
    }
  }
  return result
}

function torrentRecognition(item) {
  const expectedFiles = item.details?.inventory_plan?.expected_files || [];
  return {
    tokens: uniqueTexts(expectedFiles.flatMap(file => file.recognition?.resource_tokens || [])),
    words: uniqueTexts(expectedFiles.flatMap(file => file.recognition?.apply_words || [])),
    customizations: uniqueTexts(expectedFiles.map(file => file.recognition?.customization || '')),
    inherited: uniqueTexts(expectedFiles.flatMap(file => file.recognition?.inherited_fields || [])),
  }
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
  allQbDownloaders.value = response?.items || [];
  qbDownloaders.value = allQbDownloaders.value
    .filter(item => (item.categories || []).length > 0)
    .map(item => ({
      title: `${item.name}${item.default ? ' · 默认' : ''}${item.ready ? '' : ' · 未就绪'} · ${item.categories?.join(', ') || '无管理分类'}`,
      value: item.name,
      disabled: !item.ready,
    }));
}

async function loadSites(strict = false) {
  const response = unwrap(await props.api.get('plugin/RssAllInOne/sites'));
  if (!response?.success) {
    siteIdentities.value = [];
    if (strict) throw new Error(response?.message || '读取站点身份失败')
    return
  }
  siteIdentities.value = response.items || [];
}

async function loadActive() {
  loading.value = true;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    await loadOverview();
    if (activeTab.value === 'overview') {
      rows.value = [];
      total.value = 0;
      return
    }

    if (activeTab.value === 'vt' && vtTab.value === 'rss_tasks') {
      const [response] = await Promise.all([
        props.api.get('plugin/RssAllInOne/rss/tasks', {
          params: { offset: 0, limit: 100 },
        }).then(unwrap),
        loadQbDownloaders(),
        loadSites(false),
      ]);
      rssTasks.value = response?.items || [];
      rows.value = [];
      total.value = Number(response?.total || 0);
      return
    }

    if (activeTab.value === 'vt' && vtTab.value === 'sites') {
      await loadSites(true);
      rows.value = siteIdentities.value;
      total.value = siteIdentities.value.length;
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
      rows.value = items.map(item => {
        const recognition = torrentRecognition(item);
        return {
          ...item,
          row_key: `${item.downloader_id}:${item.info_hash}`,
          target_name: item.details?.path_plan?.inventory_files?.[0]?.path || '',
          link_target: item.details?.path_plan?.link_files?.[0]?.path || '',
          resource_tokens: recognition.tokens,
          applied_words: recognition.words,
          customizations: recognition.customizations,
          inherited_meta_fields: recognition.inherited,
        }
      });
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

async function saveRssTasks(items) {
  loading.value = true;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/rss/tasks', { items }),
    );
    if (!response?.success) {
      throw new Error(response?.message || 'RSS 任务保存失败')
    }
    rssTasks.value = response.items || [];
    total.value = Number(response.total || 0);
    successMessage.value = response.message || 'RSS 任务已保存';
    await Promise.all([loadOverview(), loadQbDownloaders()]);
  } catch (error) {
    errorMessage.value = error?.message || 'RSS 任务保存失败';
  } finally {
    loading.value = false;
  }
}

async function testRssTask(task) {
  rssTestingTaskId.value = String(task?.id || '');
  errorMessage.value = '';
  successMessage.value = '';
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/rss/test', { task }),
    );
    if (!response?.success || !response?.result) {
      throw new Error(response?.message || 'RSS 测试失败')
    }
    rssTestResult.value = response.result;
    rssTestDialog.value = true;
    successMessage.value = response.message || 'RSS 测试完成';
  } catch (error) {
    rssTestResult.value = null;
    errorMessage.value = error?.message || 'RSS 测试失败';
  } finally {
    rssTestingTaskId.value = '';
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
        force_recognition: true,
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
    empty: 'warning',
    ambiguous: 'error',
    unavailable: 'error',
    unconfigured: 'warning',
  }[state] || 'default'
}

function inventoryText(item) {
  const label = inventoryLabels[item.inventory_state] || item.inventory_state;
  const inventory = item.details?.inventory || {};
  const totalFiles = Number(inventory.total_files ?? inventory.total ?? 0);
  const existsCount = Number(inventory.exists_count ?? inventory.exists ?? 0);
  if (totalFiles > 0 && ['exists', 'partial', 'missing'].includes(item.inventory_state)) {
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
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VDialog = _resolveComponent("VDialog");

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
          _cache[9] || (_cache[9] = _createElementVNode("div", { class: "text-h6" }, "RSS一条龙", -1)),
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
            _createTextVNode("v" + _toDisplayString(overview.value.plugin?.version || '0.4.0'), 1)
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
    (successMessage.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 1,
          type: "success",
          variant: "tonal",
          class: "status-alert"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(successMessage.value), 1)
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
                  _cache[10] || (_cache[10] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "媒体记录", -1)),
                  _createElementVNode("strong", null, _toDisplayString(overview.value.counts?.media || 0), 1)
                ]),
                _: 1
              }),
              _createVNode(_component_VSheet, {
                border: "",
                class: "metric-item"
              }, {
                default: _withCtx(() => [
                  _cache[11] || (_cache[11] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "qB 快照", -1)),
                  _createElementVNode("strong", null, _toDisplayString(overview.value.counts?.torrents || 0), 1)
                ]),
                _: 1
              }),
              _createVNode(_component_VSheet, {
                border: "",
                class: "metric-item"
              }, {
                default: _withCtx(() => [
                  _cache[12] || (_cache[12] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "RSS 历史", -1)),
                  _createElementVNode("strong", null, _toDisplayString(overview.value.counts?.rss_history || 0), 1)
                ]),
                _: 1
              }),
              _createVNode(_component_VSheet, {
                border: "",
                class: "metric-item"
              }, {
                default: _withCtx(() => [
                  _cache[13] || (_cache[13] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "后台任务", -1)),
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
                _cache[14] || (_cache[14] = _createElementVNode("thead", null, [
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
                "items-per-page": -1,
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
                        default: _withCtx(() => [...(_cache[15] || (_cache[15] = [
                          _createTextVNode("全部", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VBtn, { value: "existing" }, {
                        default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                          _createTextVNode("已存在", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VBtn, { value: "pending" }, {
                        default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
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
                    default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
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
                  "items-per-page": -1,
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
                  "item.resource_info": _withCtx(({ item }) => [
                    _createElementVNode("div", _hoisted_17, [
                      _createElementVNode("span", _hoisted_18, [
                        _cache[19] || (_cache[19] = _createElementVNode("strong", null, "customization", -1)),
                        _createTextVNode(" " + _toDisplayString(item.customizations?.join(' / ') || '空'), 1)
                      ]),
                      (item.resource_tokens?.length)
                        ? (_openBlock(), _createElementBlock("span", _hoisted_19, _toDisplayString(item.resource_tokens.join(' · ')), 1))
                        : (_openBlock(), _createElementBlock("span", _hoisted_20, "未解析到资源字段")),
                      _createElementVNode("div", _hoisted_21, [
                        (item.applied_words?.length)
                          ? (_openBlock(), _createBlock(_component_VTooltip, {
                              key: 0,
                              location: "bottom",
                              "max-width": "560"
                            }, {
                              activator: _withCtx(({ props: tooltipProps }) => [
                                _createVNode(_component_VChip, _mergeProps(tooltipProps, {
                                  size: "x-small",
                                  variant: "tonal",
                                  color: "info",
                                  "prepend-icon": "mdi-tag-search-outline"
                                }), {
                                  default: _withCtx(() => [
                                    _createTextVNode(" 识别词 " + _toDisplayString(item.applied_words.length), 1)
                                  ]),
                                  _: 2
                                }, 1040)
                              ]),
                              default: _withCtx(() => [
                                _createElementVNode("div", _hoisted_22, [
                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(item.applied_words, (word) => {
                                    return (_openBlock(), _createElementBlock("code", { key: word }, _toDisplayString(word), 1))
                                  }), 128))
                                ])
                              ]),
                              _: 2
                            }, 1024))
                          : _createCommentVNode("", true),
                        (item.inherited_meta_fields?.length)
                          ? (_openBlock(), _createElementBlock("span", _hoisted_23, " 任务标题补全 " + _toDisplayString(item.inherited_meta_fields.length) + " 项 ", 1))
                          : _createCommentVNode("", true)
                      ])
                    ])
                  ]),
                  "item.inventory_state": _withCtx(({ item }) => [
                    _createVNode(_component_VChip, {
                      color: inventoryColor(item.inventory_state),
                      size: "small",
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(inventoryText(item)), 1)
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
                    _createElementVNode("div", _hoisted_24, [
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
              ? (_openBlock(), _createElementBlock("section", _hoisted_25, [
                  _createVNode(_component_VTabs, {
                    modelValue: vtTab.value,
                    "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((vtTab).value = $event)),
                    density: "compact",
                    color: "primary",
                    class: "sub-tabs"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VTab, { value: "rss_tasks" }, {
                        default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                          _createTextVNode("RSS任务", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VTab, { value: "rss_history" }, {
                        default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
                          _createTextVNode("RSS历史", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VTab, { value: "sites" }, {
                        default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
                          _createTextVNode("站点访问身份", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }, 8, ["modelValue"]),
                  (vtTab.value === 'rss_tasks')
                    ? (_openBlock(), _createBlock(RssTaskEditor, {
                        key: 0,
                        items: rssTasks.value,
                        downloaders: allQbDownloaders.value,
                        sites: siteIdentities.value,
                        loading: loading.value,
                        "testing-task-id": rssTestingTaskId.value,
                        onSave: saveRssTasks,
                        onReload: loadActive,
                        onTest: testRssTask
                      }, null, 8, ["items", "downloaders", "sites", "loading", "testing-task-id"]))
                    : (vtTab.value === 'rss_history')
                      ? (_openBlock(), _createBlock(_component_VDataTable, {
                          key: 1,
                          headers: rssHistoryHeaders,
                          items: rows.value,
                          loading: loading.value,
                          density: "compact",
                          "item-value": "id",
                          "items-per-page": -1,
                          "hide-default-footer": "",
                          class: "data-table",
                          "no-data-text": "暂无 RSS 历史"
                        }, null, 8, ["items", "loading"]))
                      : (_openBlock(), _createBlock(_component_VDataTable, {
                          key: 2,
                          headers: siteHeaders,
                          items: siteIdentities.value,
                          loading: loading.value,
                          density: "compact",
                          "item-value": "id",
                          "items-per-page": -1,
                          "hide-default-footer": "",
                          class: "data-table",
                          "no-data-text": "暂无可用站点身份"
                        }, {
                          "item.enabled": _withCtx(({ item }) => [
                            _createVNode(_component_VChip, {
                              color: item.enabled ? 'success' : 'default',
                              size: "small",
                              variant: "tonal"
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(item.enabled ? '已启用' : '未启用'), 1)
                              ]),
                              _: 2
                            }, 1032, ["color"])
                          ]),
                          "item.ready": _withCtx(({ item }) => [
                            _createVNode(_component_VChip, {
                              color: item.ready ? 'success' : 'warning',
                              size: "small",
                              variant: "tonal"
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(item.ready ? '可用' : '未就绪'), 1)
                              ]),
                              _: 2
                            }, 1032, ["color"])
                          ]),
                          _: 1
                        }, 8, ["items", "loading"]))
                ]))
              : (activeTab.value === 'tasks')
                ? (_openBlock(), _createElementBlock("section", _hoisted_26, [
                    _createElementVNode("div", _hoisted_27, _toDisplayString(total.value) + " 个后台任务", 1),
                    _createVNode(_component_VDataTable, {
                      headers: taskHeaders,
                      items: rows.value,
                      loading: loading.value,
                      density: "compact",
                      "item-value": "id",
                      "items-per-page": -1,
                      "hide-default-footer": "",
                      class: "data-table",
                      "no-data-text": "暂无后台任务"
                    }, null, 8, ["items", "loading"])
                  ]))
                : _createCommentVNode("", true)
    ]),
    _createVNode(_component_VDialog, {
      modelValue: rssTestDialog.value,
      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((rssTestDialog).value = $event)),
      "max-width": "1280"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, null, {
          default: _withCtx(() => [
            _createVNode(_component_VCardTitle, { class: "rss-test-title" }, {
              default: _withCtx(() => [
                _createVNode(_component_VIcon, {
                  icon: "mdi-rss",
                  color: "primary"
                }),
                _createElementVNode("span", null, _toDisplayString(rssTestResult.value?.task?.name || 'RSS 测试结果'), 1),
                _createVNode(_component_VSpacer),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  variant: "text",
                  "aria-label": "关闭",
                  onClick: _cache[7] || (_cache[7] = $event => (rssTestDialog.value = false))
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VDivider),
            (rssTestResult.value)
              ? (_openBlock(), _createBlock(_component_VCardText, {
                  key: 0,
                  class: "rss-test-content"
                }, {
                  default: _withCtx(() => [
                    _createElementVNode("div", _hoisted_28, [
                      _createVNode(_component_VChip, {
                        size: "small",
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(_toDisplayString(rssTestResult.value.feed?.type?.toUpperCase() || 'RSS'), 1)
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_VChip, {
                        size: "small",
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(" 共 " + _toDisplayString(rssTestResult.value.counts?.total || 0) + " 条 ", 1)
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_VChip, {
                        size: "small",
                        color: "success",
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(" 可处理 " + _toDisplayString(rssTestResult.value.counts?.ready || 0), 1)
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_VChip, {
                        size: "small",
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(" 已过滤 " + _toDisplayString(rssTestResult.value.counts?.filtered || 0), 1)
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_VChip, {
                        size: "small",
                        color: "warning",
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(" 缺少种子链接 " + _toDisplayString(rssTestResult.value.counts?.missing_enclosure || 0), 1)
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_VChip, {
                        size: "small",
                        color: "info",
                        variant: "tonal"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(" 重复 " + _toDisplayString(rssTestResult.value.counts?.duplicate || 0), 1)
                        ]),
                        _: 1
                      }),
                      (rssTestResult.value.truncated)
                        ? (_openBlock(), _createBlock(_component_VChip, {
                            key: 0,
                            size: "small",
                            color: "warning",
                            variant: "tonal"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(" 仅显示前 " + _toDisplayString(rssTestResult.value.items?.length || 0) + " 条 ", 1)
                            ]),
                            _: 1
                          }))
                        : _createCommentVNode("", true)
                    ]),
                    (rssTestResult.value.feed?.title)
                      ? (_openBlock(), _createElementBlock("div", _hoisted_29, _toDisplayString(rssTestResult.value.feed.title), 1))
                      : _createCommentVNode("", true),
                    _createElementVNode("code", _hoisted_30, _toDisplayString(rssTestResult.value.feed?.final_url_masked), 1),
                    _createVNode(_component_VDataTable, {
                      headers: rssTestHeaders,
                      items: rssTestResult.value.items || [],
                      density: "compact",
                      "item-value": "row_key",
                      "items-per-page": -1,
                      "hide-default-footer": "",
                      class: "data-table rss-test-table",
                      "no-data-text": "RSS 中没有可解析条目"
                    }, {
                      "item.status": _withCtx(({ item }) => [
                        _createVNode(_component_VChip, {
                          color: rssTestColor(item.status),
                          size: "small",
                          variant: "tonal"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(rssTestLabels[item.status] || item.status), 1)
                          ]),
                          _: 2
                        }, 1032, ["color"])
                      ]),
                      "item.enclosure_url_masked": _withCtx(({ item }) => [
                        _createElementVNode("code", _hoisted_31, _toDisplayString(item.enclosure_url_masked || '-'), 1)
                      ]),
                      "item.detail_url_masked": _withCtx(({ item }) => [
                        _createElementVNode("code", _hoisted_32, _toDisplayString(item.detail_url_masked || '-'), 1)
                      ]),
                      _: 1
                    }, 8, ["items"])
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true)
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"])
  ]))
}
}

};
const AppPage = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-4c745f31"]]);

export { AppPage as default };
