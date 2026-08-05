import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {toDisplayString:_toDisplayString$3,createElementVNode:_createElementVNode$3,resolveComponent:_resolveComponent$3,createVNode:_createVNode$3,createTextVNode:_createTextVNode$3,withCtx:_withCtx$3,mergeProps:_mergeProps$2,openBlock:_openBlock$3,createBlock:_createBlock$3,createCommentVNode:_createCommentVNode$3,renderList:_renderList$1,Fragment:_Fragment$1,createElementBlock:_createElementBlock$2,withModifiers:_withModifiers$1} = await importShared('vue');


const _hoisted_1$3 = { class: "rss-editor" };
const _hoisted_2$3 = { class: "rss-toolbar" };
const _hoisted_3$2 = { class: "text-caption text-medium-emphasis" };
const _hoisted_4$2 = { class: "task-title" };
const _hoisted_5$2 = { class: "switch-grid" };

const {computed: computed$3,ref: ref$1,watch: watch$2} = await importShared('vue');



const _sfc_main$3 = {
  __name: 'RssTaskEditor',
  props: {
  items: { type: Array, default: () => [] },
  downloaders: { type: Array, default: () => [] },
  sites: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  testingTaskId: { type: String, default: '' },
  runningTaskId: { type: String, default: '' },
  rssEnabled: { type: Boolean, default: true },
  controlling: { type: Boolean, default: false },
},
  emits: ['save', 'reload', 'test', 'run', 'control'],
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
  { key: 'realtime_hardlink_enabled', label: '完成后创建实时硬链接' },
  { key: 'rename_enabled', label: '重命名' },
  { key: 'download_enabled', label: '下载' },
  { key: 'delete_files', label: '删除文件' },
];

const downloaderOptions = computed$3(() => props.downloaders.map(item => ({
  title: `${item.name}${item.default ? ' · 默认' : ''}${item.ready ? '' : ' · 未就绪'}`,
  value: item.name,
  disabled: !item.enabled,
})));

const siteOptions = computed$3(() => [
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
    realtime_hardlink_enabled: false,
    realtime_source_root: '',
    realtime_link_root: '',
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

watch$2(
  () => props.items,
  value => {
    tasks.value = (value || []).map(normalizeTask);
    expanded.value = tasks.value.length === 1 ? [tasks.value[0].id] : [];
  },
  { immediate: true, deep: true },
);

return (_ctx, _cache) => {
  const _component_VSpacer = _resolveComponent$3("VSpacer");
  const _component_VBtn = _resolveComponent$3("VBtn");
  const _component_VTooltip = _resolveComponent$3("VTooltip");
  const _component_VAlert = _resolveComponent$3("VAlert");
  const _component_VSwitch = _resolveComponent$3("VSwitch");
  const _component_VChip = _resolveComponent$3("VChip");
  const _component_VExpansionPanelTitle = _resolveComponent$3("VExpansionPanelTitle");
  const _component_VTextField = _resolveComponent$3("VTextField");
  const _component_VCol = _resolveComponent$3("VCol");
  const _component_VSelect = _resolveComponent$3("VSelect");
  const _component_VTextarea = _resolveComponent$3("VTextarea");
  const _component_VRow = _resolveComponent$3("VRow");
  const _component_VDivider = _resolveComponent$3("VDivider");
  const _component_VExpansionPanelText = _resolveComponent$3("VExpansionPanelText");
  const _component_VExpansionPanel = _resolveComponent$3("VExpansionPanel");
  const _component_VExpansionPanels = _resolveComponent$3("VExpansionPanels");

  return (_openBlock$3(), _createElementBlock$2("div", _hoisted_1$3, [
    _createElementVNode$3("div", _hoisted_2$3, [
      _createElementVNode$3("span", _hoisted_3$2, _toDisplayString$3(tasks.value.length) + " 条任务", 1),
      _createVNode$3(_component_VSpacer),
      _createVNode$3(_component_VBtn, {
        "prepend-icon": __props.rssEnabled ? 'mdi-pause-circle-outline' : 'mdi-play-circle-outline',
        color: __props.rssEnabled ? 'warning' : 'success',
        variant: "tonal",
        loading: __props.controlling,
        onClick: _cache[0] || (_cache[0] = $event => (emit('control', !__props.rssEnabled)))
      }, {
        default: _withCtx$3(() => [
          _createTextVNode$3(_toDisplayString$3(__props.rssEnabled ? '暂停 RSS 调度' : '恢复 RSS 调度'), 1)
        ]),
        _: 1
      }, 8, ["prepend-icon", "color", "loading"]),
      _createVNode$3(_component_VTooltip, { text: "重新读取" }, {
        activator: _withCtx$3(({ props: tooltipProps }) => [
          _createVNode$3(_component_VBtn, _mergeProps$2(tooltipProps, {
            icon: "mdi-refresh",
            variant: "text",
            loading: __props.loading,
            "aria-label": "重新读取",
            onClick: _cache[1] || (_cache[1] = $event => (emit('reload')))
          }), null, 16, ["loading"])
        ]),
        _: 1
      }),
      _createVNode$3(_component_VBtn, {
        "prepend-icon": "mdi-plus",
        variant: "text",
        onClick: addTask
      }, {
        default: _withCtx$3(() => [...(_cache[4] || (_cache[4] = [
          _createTextVNode$3(" 添加任务 ", -1)
        ]))]),
        _: 1
      }),
      _createVNode$3(_component_VBtn, {
        "prepend-icon": "mdi-content-save",
        color: "primary",
        variant: "tonal",
        loading: __props.loading,
        onClick: saveTasks
      }, {
        default: _withCtx$3(() => [...(_cache[5] || (_cache[5] = [
          _createTextVNode$3(" 保存 ", -1)
        ]))]),
        _: 1
      }, 8, ["loading"])
    ]),
    (tasks.value.length === 0)
      ? (_openBlock$3(), _createBlock$3(_component_VAlert, {
          key: 0,
          type: "info",
          variant: "tonal"
        }, {
          default: _withCtx$3(() => [...(_cache[6] || (_cache[6] = [
            _createTextVNode$3(" 暂无 RSS 任务 ", -1)
          ]))]),
          _: 1
        }))
      : (_openBlock$3(), _createBlock$3(_component_VExpansionPanels, {
          key: 1,
          modelValue: expanded.value,
          "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((expanded).value = $event)),
          multiple: "",
          class: "task-panels"
        }, {
          default: _withCtx$3(() => [
            (_openBlock$3(true), _createElementBlock$2(_Fragment$1, null, _renderList$1(tasks.value, (task, index) => {
              return (_openBlock$3(), _createBlock$3(_component_VExpansionPanel, {
                key: task.id,
                value: task.id
              }, {
                default: _withCtx$3(() => [
                  _createVNode$3(_component_VExpansionPanelTitle, null, {
                    default: _withCtx$3(() => [
                      _createElementVNode$3("div", _hoisted_4$2, [
                        _createVNode$3(_component_VSwitch, {
                          modelValue: task.enabled,
                          "onUpdate:modelValue": $event => ((task.enabled) = $event),
                          density: "compact",
                          "hide-details": "",
                          color: "primary",
                          onClick: _cache[2] || (_cache[2] = _withModifiers$1(() => {}, ["stop"]))
                        }, null, 8, ["modelValue", "onUpdate:modelValue"]),
                        _createElementVNode$3("strong", null, _toDisplayString$3(task.name || `RSS任务 ${index + 1}`), 1),
                        (task.config.qb_category)
                          ? (_openBlock$3(), _createBlock$3(_component_VChip, {
                              key: 0,
                              size: "small",
                              variant: "tonal"
                            }, {
                              default: _withCtx$3(() => [
                                _createTextVNode$3(_toDisplayString$3(task.config.qb_category), 1)
                              ]),
                              _: 2
                            }, 1024))
                          : _createCommentVNode$3("", true),
                        _createVNode$3(_component_VSpacer),
                        _createVNode$3(_component_VTooltip, { text: "立即执行已保存配置" }, {
                          activator: _withCtx$3(({ props: tooltipProps }) => [
                            _createVNode$3(_component_VBtn, _mergeProps$2({ ref_for: true }, tooltipProps, {
                              icon: "mdi-play-circle-outline",
                              size: "small",
                              variant: "text",
                              color: "success",
                              loading: __props.runningTaskId === task.id,
                              disabled: !__props.rssEnabled || !task.enabled || !String(task.config.rss_url || '').trim(),
                              "aria-label": "立即执行 RSS",
                              onClick: _withModifiers$1($event => (emit('run', task)), ["stop"])
                            }), null, 16, ["loading", "disabled", "onClick"])
                          ]),
                          _: 2
                        }, 1024),
                        _createVNode$3(_component_VTooltip, { text: "测试 RSS" }, {
                          activator: _withCtx$3(({ props: tooltipProps }) => [
                            _createVNode$3(_component_VBtn, _mergeProps$2({ ref_for: true }, tooltipProps, {
                              icon: "mdi-flask-outline",
                              size: "small",
                              variant: "text",
                              color: "primary",
                              loading: __props.testingTaskId === task.id,
                              disabled: !String(task.config.rss_url || '').trim(),
                              "aria-label": "测试 RSS",
                              onClick: _withModifiers$1($event => (testTask(task, index)), ["stop"])
                            }), null, 16, ["loading", "disabled", "onClick"])
                          ]),
                          _: 2
                        }, 1024),
                        _createVNode$3(_component_VTooltip, { text: "删除任务" }, {
                          activator: _withCtx$3(({ props: tooltipProps }) => [
                            _createVNode$3(_component_VBtn, _mergeProps$2({ ref_for: true }, tooltipProps, {
                              icon: "mdi-delete-outline",
                              size: "small",
                              variant: "text",
                              color: "error",
                              "aria-label": "删除任务",
                              onClick: _withModifiers$1($event => (removeTask(index)), ["stop"])
                            }), null, 16, ["onClick"])
                          ]),
                          _: 2
                        }, 1024)
                      ])
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode$3(_component_VExpansionPanelText, null, {
                    default: _withCtx$3(() => [
                      _createVNode$3(_component_VRow, { dense: "" }, {
                        default: _withCtx$3(() => [
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "4"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
                                modelValue: task.name,
                                "onUpdate:modelValue": $event => ((task.name) = $event),
                                label: "任务名称"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "8"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
                                modelValue: task.config.rss_url,
                                "onUpdate:modelValue": $event => ((task.config.rss_url) = $event),
                                label: "RSS URL"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "4"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VSelect, {
                                modelValue: task.config.qb_downloader,
                                "onUpdate:modelValue": $event => ((task.config.qb_downloader) = $event),
                                items: downloaderOptions.value,
                                label: "QB下载器"
                              }, null, 8, ["modelValue", "onUpdate:modelValue", "items"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "4"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
                                modelValue: task.config.qb_category,
                                "onUpdate:modelValue": $event => ((task.config.qb_category) = $event),
                                label: "QB分类"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "4"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
                                modelValue: task.config.save_path,
                                "onUpdate:modelValue": $event => ((task.config.save_path) = $event),
                                label: "保存路径"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
                                modelValue: task.config.rss_cron,
                                "onUpdate:modelValue": $event => ((task.config.rss_cron) = $event),
                                label: "RSS周期 (CRON)"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
                                modelValue: task.config.start_cron,
                                "onUpdate:modelValue": $event => ((task.config.start_cron) = $event),
                                label: "开始任务 CRON"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
                                modelValue: task.config.name_contains,
                                "onUpdate:modelValue": $event => ((task.config.name_contains) = $event),
                                label: "限制条件 (名称包含)"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "3"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
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
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "3"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
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
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextarea, {
                                modelValue: task.config.path_mappings,
                                "onUpdate:modelValue": $event => ((task.config.path_mappings) = $event),
                                label: "路径映射",
                                rows: "3",
                                "auto-grow": ""
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextarea, {
                                modelValue: task.config.rename_rules,
                                "onUpdate:modelValue": $event => ((task.config.rename_rules) = $event),
                                label: "重命名规则",
                                rows: "3",
                                "auto-grow": ""
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VSelect, {
                                modelValue: task.config.site_id,
                                "onUpdate:modelValue": $event => ((task.config.site_id) = $event),
                                items: siteOptions.value,
                                label: "站点访问身份"
                              }, null, 8, ["modelValue", "onUpdate:modelValue", "items"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
                                modelValue: task.config.cn_keywords,
                                "onUpdate:modelValue": $event => ((task.config.cn_keywords) = $event),
                                label: "国语关键词"
                              }, null, 8, ["modelValue", "onUpdate:modelValue"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
                                modelValue: task.config.realtime_source_root,
                                "onUpdate:modelValue": $event => ((task.config.realtime_source_root) = $event),
                                label: "实时硬链接源根目录",
                                placeholder: "/SSD/QB目录/REMUX/CHD",
                                disabled: !task.config.realtime_hardlink_enabled
                              }, null, 8, ["modelValue", "onUpdate:modelValue", "disabled"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode$3(_component_VCol, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx$3(() => [
                              _createVNode$3(_component_VTextField, {
                                modelValue: task.config.realtime_link_root,
                                "onUpdate:modelValue": $event => ((task.config.realtime_link_root) = $event),
                                label: "实时硬链接目标根目录",
                                placeholder: "/SSD/QB目录/REMUX/CHDlink",
                                disabled: !task.config.realtime_hardlink_enabled
                              }, null, 8, ["modelValue", "onUpdate:modelValue", "disabled"])
                            ]),
                            _: 2
                          }, 1024)
                        ]),
                        _: 2
                      }, 1024),
                      _createVNode$3(_component_VDivider, { class: "mb-3" }),
                      _createElementVNode$3("div", _hoisted_5$2, [
                        (_openBlock$3(), _createElementBlock$2(_Fragment$1, null, _renderList$1(booleanOptions, (option) => {
                          return _createVNode$3(_component_VSwitch, {
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
const RssTaskEditor = /*#__PURE__*/_export_sfc(_sfc_main$3, [['__scopeId',"data-v-fa67f210"]]);

const {resolveComponent:_resolveComponent$2,createVNode:_createVNode$2,createElementVNode:_createElementVNode$2,withCtx:_withCtx$2,openBlock:_openBlock$2,createBlock:_createBlock$2,createCommentVNode:_createCommentVNode$2,createElementBlock:_createElementBlock$1,mergeProps:_mergeProps$1,withModifiers:_withModifiers,toDisplayString:_toDisplayString$2,createTextVNode:_createTextVNode$2,normalizeClass:_normalizeClass} = await importShared('vue');


const _hoisted_1$2 = { class: "poster-area" };
const _hoisted_2$2 = { class: "poster-placeholder" };
const _hoisted_3$1 = {
  key: 1,
  class: "poster-placeholder"
};
const _hoisted_4$1 = { class: "chip-row" };
const _hoisted_5$1 = {
  key: 0,
  class: "source-name"
};
const _hoisted_6$1 = {
  key: 1,
  class: "size-label"
};
const _hoisted_7$1 = {
  key: 2,
  class: "target-name"
};

const {computed: computed$2} = await importShared('vue');



const _sfc_main$2 = {
  __name: 'MediaPosterCard',
  props: {
  item: { type: Object, required: true },
  mode: { type: String, default: 'qb' },
  selected: Boolean,
  busy: Boolean,
},
  emits: ['toggle', 'refresh', 'edit', 'delete'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const details = computed$2(() => props.item.details || {});
const inventory = computed$2(() => details.value.inventory || {});
const media = computed$2(() => details.value.media || {});
const override = computed$2(() => details.value.manual_override || {});
const title = computed$2(() => props.item.media_title || props.item.title || props.item.source_name || props.item.name || '未识别');
const sourceName = computed$2(() => props.item.source_name || props.item.name || '');
const poster = computed$2(() => props.item.poster || media.value.poster_path || media.value.poster || '');
const sourceUrl = computed$2(() => {
  const value = props.item.comment_url
    || props.item.source_url_masked
    || details.value.rss_source?.detail_url_masked
    || details.value.comment_url
    || details.value.source_url
    || '';
  return usableSourceUrl(value)
});
const mediaType = computed$2(() => props.item.media_type || override.value.media_type || '');
const tmdbUrl = computed$2(() => {
  const tmdbId = Number(props.item.tmdb_id || override.value.tmdb_id || 0);
  if (!tmdbId) return ''
  return `https://www.themoviedb.org/${mediaType.value === 'movie' ? 'movie' : 'tv'}/${tmdbId}`
});
const totalFiles = computed$2(() => Number(inventory.value.total_files ?? inventory.value.total ?? 0));
const existsCount = computed$2(() => Number(inventory.value.exists_count ?? inventory.value.exists ?? 0));
const customization = computed$2(() => {
  const expected = details.value.inventory_plan?.expected_files || [];
  return [...new Set(expected.map(file => file.recognition?.customization).filter(Boolean))].join('@')
});
const customizationLabel = computed$2(() => customization.value.replaceAll('@', '@\u200b'));
const resourceTokens = computed$2(() => {
  const expected = details.value.inventory_plan?.expected_files || [];
  return [...new Set(expected.flatMap(file => file.recognition?.resource_tokens || []).filter(Boolean))]
});
const resolution = computed$2(() => resourceTokens.value.find(value => /^\d{3,4}p$/i.test(value)) || '');
const mediaCategory = computed$2(() => props.item.media_category || details.value.path_plan?.category || props.item.category || '');
const plannedName = computed$2(() => details.value.inventory_plan?.expected_directory || props.item.target_name || '');
const sizeText = computed$2(() => formatSize(Number(props.item.size || details.value.torrent?.size || 0)));
const isImported = computed$2(() => props.mode === 'imported');
const showDelete = computed$2(() => props.mode === 'pending');
const showEdit = computed$2(() => !isImported.value);
const status = computed$2(() => {
  if (props.mode === 'qb') {
    if (props.item.recognition_state === 'unidentified') return { text: '未识别', color: 'error' }
    if (props.item.inventory_state === 'exists') return { text: '已存在', color: 'success' }
    if (details.value.import_control?.import_enabled === false) return { text: '仅下载', color: 'orange' }
    return { text: '待入库', color: 'info' }
  }
  const state = props.item.state || '';
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
});
const inventoryText = computed$2(() => {
  const folderStatus = inventory.value.folder_status || inventory.value.folder?.status || '';
  if (folderStatus === 'ambiguous' || props.item.inventory_state === 'ambiguous') return '目录冲突'
  if (folderStatus === 'exists' || ['exists', 'partial'].includes(props.item.inventory_state)) {
    return `目录已存在（${existsCount.value}/${totalFiles.value}）`
  }
  return `目录未建立${totalFiles.value ? `（0/${totalFiles.value}）` : ''}`
});
const inventoryClass = computed$2(() => {
  if (inventoryText.value === '目录冲突') return 'inventory-warning'
  return inventoryText.value.startsWith('目录已存在') ? 'inventory-ok' : 'inventory-missing'
});

function formatSize(bytes) {
  if (!bytes) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit >= 3 ? 2 : 1)} ${units[unit]}`
}

function openLink(url) {
  if (url) window.open(url, '_blank', 'noopener,noreferrer');
}

function usableSourceUrl(value) {
  const text = String(value || '').trim();
  if (!/^https?:\/\//i.test(text)) return ''
  try {
    const url = new URL(text);
    url.username = '';
    url.password = '';
    for (const [key, itemValue] of [...url.searchParams.entries()]) {
      if (itemValue.includes('***')) url.searchParams.delete(key);
    }
    return url.toString()
  } catch {
    return ''
  }
}

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent$2("VIcon");
  const _component_VImg = _resolveComponent$2("VImg");
  const _component_VTooltip = _resolveComponent$2("VTooltip");
  const _component_VBtn = _resolveComponent$2("VBtn");
  const _component_VChip = _resolveComponent$2("VChip");
  const _component_VCardText = _resolveComponent$2("VCardText");
  const _component_VCard = _resolveComponent$2("VCard");

  return (_openBlock$2(), _createBlock$2(_component_VCard, {
    class: _normalizeClass(["media-poster-card", { selected: __props.selected }]),
    elevation: "0",
    onClick: _cache[7] || (_cache[7] = $event => (emit('toggle', __props.item)))
  }, {
    default: _withCtx$2(() => [
      _createElementVNode$2("div", _hoisted_1$2, [
        (poster.value)
          ? (_openBlock$2(), _createBlock$2(_component_VImg, {
              key: 0,
              src: poster.value,
              cover: "",
              class: "poster-image"
            }, {
              error: _withCtx$2(() => [
                _createElementVNode$2("div", _hoisted_2$2, [
                  _createVNode$2(_component_VIcon, {
                    icon: "mdi-broken-image",
                    size: "42"
                  })
                ])
              ]),
              _: 1
            }, 8, ["src"]))
          : (_openBlock$2(), _createElementBlock$1("div", _hoisted_3$1, [
              _createVNode$2(_component_VIcon, {
                icon: __props.item.recognition_state === 'unidentified' ? 'mdi-broken-image' : 'mdi-movie-open-outline',
                size: "42"
              }, null, 8, ["icon"])
            ])),
        _createElementVNode$2("div", {
          class: "poster-left-actions",
          onClick: _cache[2] || (_cache[2] = _withModifiers(() => {}, ["stop"]))
        }, [
          (__props.item.rolled_back)
            ? (_openBlock$2(), _createBlock$2(_component_VTooltip, {
                key: 0,
                text: "已回退"
              }, {
                activator: _withCtx$2(({ props: tooltipProps }) => [
                  _createElementVNode$2("span", _mergeProps$1(tooltipProps, { class: "corner-badge rollback" }), "R", 16)
                ]),
                _: 1
              }))
            : _createCommentVNode$2("", true),
          (__props.item.failure_message || __props.item.recognition_error)
            ? (_openBlock$2(), _createBlock$2(_component_VTooltip, {
                key: 1,
                text: __props.item.failure_message || __props.item.recognition_error || '入库失败'
              }, {
                activator: _withCtx$2(({ props: tooltipProps }) => [
                  _createElementVNode$2("span", _mergeProps$1(tooltipProps, { class: "corner-badge failure" }), "!", 16)
                ]),
                _: 1
              }, 8, ["text"]))
            : _createCommentVNode$2("", true),
          (sourceUrl.value)
            ? (_openBlock$2(), _createBlock$2(_component_VTooltip, {
                key: 2,
                text: "打开来源页面"
              }, {
                activator: _withCtx$2(({ props: tooltipProps }) => [
                  _createElementVNode$2("button", _mergeProps$1(tooltipProps, {
                    type: "button",
                    class: "corner-badge source",
                    onClick: _cache[0] || (_cache[0] = $event => (openLink(sourceUrl.value)))
                  }), "P", 16)
                ]),
                _: 1
              }))
            : _createCommentVNode$2("", true),
          (tmdbUrl.value && !isImported.value)
            ? (_openBlock$2(), _createBlock$2(_component_VTooltip, {
                key: 3,
                text: "打开 TMDB"
              }, {
                activator: _withCtx$2(({ props: tooltipProps }) => [
                  _createElementVNode$2("button", _mergeProps$1(tooltipProps, {
                    type: "button",
                    class: "corner-badge tmdb",
                    onClick: _cache[1] || (_cache[1] = $event => (openLink(tmdbUrl.value)))
                  }), "T", 16)
                ]),
                _: 1
              }))
            : _createCommentVNode$2("", true)
        ]),
        _createElementVNode$2("div", {
          class: "poster-right-actions",
          onClick: _cache[6] || (_cache[6] = _withModifiers(() => {}, ["stop"]))
        }, [
          (showDelete.value)
            ? (_openBlock$2(), _createBlock$2(_component_VTooltip, {
                key: 0,
                text: "删除插件记录"
              }, {
                activator: _withCtx$2(({ props: tooltipProps }) => [
                  _createVNode$2(_component_VBtn, _mergeProps$1(tooltipProps, {
                    icon: "mdi-close",
                    size: "x-small",
                    class: "poster-action",
                    disabled: __props.busy,
                    onClick: _cache[3] || (_cache[3] = $event => (emit('delete', __props.item)))
                  }), null, 16, ["disabled"])
                ]),
                _: 1
              }))
            : _createCommentVNode$2("", true),
          _createVNode$2(_component_VTooltip, { text: "刷新" }, {
            activator: _withCtx$2(({ props: tooltipProps }) => [
              _createVNode$2(_component_VBtn, _mergeProps$1(tooltipProps, {
                icon: "mdi-refresh",
                size: "x-small",
                class: "poster-action",
                loading: __props.busy,
                onClick: _cache[4] || (_cache[4] = $event => (emit('refresh', __props.item)))
              }), null, 16, ["loading"])
            ]),
            _: 1
          }),
          (showEdit.value)
            ? (_openBlock$2(), _createBlock$2(_component_VTooltip, {
                key: 1,
                text: "人工识别"
              }, {
                activator: _withCtx$2(({ props: tooltipProps }) => [
                  _createVNode$2(_component_VBtn, _mergeProps$1(tooltipProps, {
                    icon: "mdi-pencil",
                    size: "x-small",
                    class: "poster-action",
                    disabled: __props.busy,
                    onClick: _cache[5] || (_cache[5] = $event => (emit('edit', __props.item)))
                  }), null, 16, ["disabled"])
                ]),
                _: 1
              }))
            : _createCommentVNode$2("", true)
        ]),
        (Number(details.value.version_count || 0) > 1)
          ? (_openBlock$2(), _createBlock$2(_component_VChip, {
              key: 2,
              class: "version-chip",
              size: "x-small",
              color: "info"
            }, {
              default: _withCtx$2(() => [
                _createTextVNode$2(_toDisplayString$2(details.value.version_count) + "in1 ", 1)
              ]),
              _: 1
            }))
          : _createCommentVNode$2("", true)
      ]),
      _createVNode$2(_component_VCardText, { class: "card-body" }, {
        default: _withCtx$2(() => [
          _createElementVNode$2("h3", null, _toDisplayString$2(title.value), 1),
          _createElementVNode$2("div", _hoisted_4$1, [
            _createVNode$2(_component_VChip, {
              size: "x-small",
              variant: "flat",
              class: _normalizeClass(['info-chip', 'status-chip', `tag-${status.value.color}`])
            }, {
              default: _withCtx$2(() => [
                _createTextVNode$2(_toDisplayString$2(status.value.text), 1)
              ]),
              _: 1
            }, 8, ["class"]),
            (mediaType.value !== 'movie' && __props.item.season !== null && __props.item.season !== undefined)
              ? (_openBlock$2(), _createBlock$2(_component_VChip, {
                  key: 0,
                  size: "x-small",
                  variant: "flat",
                  class: "info-chip season-chip"
                }, {
                  default: _withCtx$2(() => [
                    _createTextVNode$2(_toDisplayString$2(Number(__props.item.season) === 0 ? '特别篇(S00)' : `第${Number(__props.item.season)}季`), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode$2("", true),
            (resolution.value)
              ? (_openBlock$2(), _createBlock$2(_component_VChip, {
                  key: 1,
                  size: "x-small",
                  variant: "flat",
                  class: "info-chip resolution-chip"
                }, {
                  default: _withCtx$2(() => [
                    _createTextVNode$2(_toDisplayString$2(resolution.value), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode$2("", true),
            (mediaCategory.value)
              ? (_openBlock$2(), _createBlock$2(_component_VChip, {
                  key: 2,
                  size: "x-small",
                  variant: "flat",
                  class: "info-chip category-chip"
                }, {
                  default: _withCtx$2(() => [
                    _createTextVNode$2(_toDisplayString$2(mediaCategory.value), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode$2("", true),
            (customization.value)
              ? (_openBlock$2(), _createBlock$2(_component_VChip, {
                  key: 3,
                  size: "x-small",
                  variant: "flat",
                  class: "info-chip customization-chip"
                }, {
                  default: _withCtx$2(() => [
                    _createTextVNode$2(_toDisplayString$2(customizationLabel.value), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode$2("", true)
          ]),
          (sourceName.value)
            ? (_openBlock$2(), _createElementBlock$1("p", _hoisted_5$1, "源: " + _toDisplayString$2(sourceName.value), 1))
            : _createCommentVNode$2("", true),
          (sizeText.value)
            ? (_openBlock$2(), _createElementBlock$1("span", _hoisted_6$1, "大小: " + _toDisplayString$2(sizeText.value), 1))
            : _createCommentVNode$2("", true),
          (plannedName.value && __props.item.recognition_state !== 'unidentified')
            ? (_openBlock$2(), _createElementBlock$1("p", _hoisted_7$1, _toDisplayString$2(plannedName.value), 1))
            : _createCommentVNode$2("", true),
          (plannedName.value)
            ? (_openBlock$2(), _createElementBlock$1("p", {
                key: 3,
                class: _normalizeClass(["inventory-line", inventoryClass.value])
              }, _toDisplayString$2(inventoryText.value), 3))
            : _createCommentVNode$2("", true)
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["class"]))
}
}

};
const MediaPosterCard = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-8c9b15c8"]]);

const {resolveComponent:_resolveComponent$1,createVNode:_createVNode$1,createElementVNode:_createElementVNode$1,withCtx:_withCtx$1,toDisplayString:_toDisplayString$1,createTextVNode:_createTextVNode$1,openBlock:_openBlock$1,createBlock:_createBlock$1,createCommentVNode:_createCommentVNode$1} = await importShared('vue');


const _hoisted_1$1 = { class: "source-title" };
const _hoisted_2$1 = { class: "automatic-category" };

const {computed: computed$1,reactive,watch: watch$1} = await importShared('vue');



const _sfc_main$1 = {
  __name: 'ManualIdentifyDialog',
  props: {
  modelValue: Boolean,
  item: { type: Object, default: null },
  categories: { type: Array, default: () => [] },
  loading: Boolean,
},
  emits: ['update:modelValue', 'save'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;
const form = reactive({ media_type: 'tv', tmdb_id: '', season: 1, category: '' });
const open = computed$1({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
});
const categoryItems = computed$1(() => [
  { title: '自动分类（MoviePilot）', value: '' },
  ...props.categories.map(value => ({ title: value, value })),
]);
const automaticCategory = computed$1(() => props.item?.details?.automatic_category || props.item?.category || '未分类');

watch$1(() => [props.modelValue, props.item], ([visible]) => {
  if (!visible || !props.item) return
  const override = props.item.details?.manual_override || {};
  form.media_type = override.media_type || props.item.media_type || 'tv';
  form.tmdb_id = override.tmdb_id || props.item.tmdb_id || '';
  form.season = override.season ?? props.item.season ?? 1;
  form.category = override.category || '';
}, { immediate: true });

function submit() {
  emit('save', {
    downloader_id: props.item?.downloader_id,
    info_hash: props.item?.info_hash,
    media_type: form.media_type,
    tmdb_id: Number(form.tmdb_id || 0),
    season: form.media_type === 'tv' ? Number(form.season || 0) : null,
    category: form.category,
  });
}

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent$1("VIcon");
  const _component_VSpacer = _resolveComponent$1("VSpacer");
  const _component_VBtn = _resolveComponent$1("VBtn");
  const _component_VCardTitle = _resolveComponent$1("VCardTitle");
  const _component_VDivider = _resolveComponent$1("VDivider");
  const _component_VBtnToggle = _resolveComponent$1("VBtnToggle");
  const _component_VTextField = _resolveComponent$1("VTextField");
  const _component_VSelect = _resolveComponent$1("VSelect");
  const _component_VCardText = _resolveComponent$1("VCardText");
  const _component_VCardActions = _resolveComponent$1("VCardActions");
  const _component_VCard = _resolveComponent$1("VCard");
  const _component_VDialog = _resolveComponent$1("VDialog");

  return (_openBlock$1(), _createBlock$1(_component_VDialog, {
    modelValue: open.value,
    "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((open).value = $event)),
    "max-width": "520",
    persistent: ""
  }, {
    default: _withCtx$1(() => [
      _createVNode$1(_component_VCard, { class: "identify-dialog" }, {
        default: _withCtx$1(() => [
          _createVNode$1(_component_VCardTitle, { class: "dialog-title" }, {
            default: _withCtx$1(() => [
              _createVNode$1(_component_VIcon, {
                icon: "mdi-movie-edit-outline",
                color: "primary"
              }),
              _cache[7] || (_cache[7] = _createElementVNode$1("span", null, "人工识别", -1)),
              _createVNode$1(_component_VSpacer),
              _createVNode$1(_component_VBtn, {
                icon: "mdi-close",
                variant: "text",
                disabled: __props.loading,
                "aria-label": "关闭",
                onClick: _cache[0] || (_cache[0] = $event => (open.value = false))
              }, null, 8, ["disabled"])
            ]),
            _: 1
          }),
          _createVNode$1(_component_VDivider),
          _createVNode$1(_component_VCardText, { class: "dialog-form" }, {
            default: _withCtx$1(() => [
              _createElementVNode$1("p", _hoisted_1$1, _toDisplayString$1(__props.item?.name || __props.item?.source_name || __props.item?.title), 1),
              _createVNode$1(_component_VBtnToggle, {
                modelValue: form.media_type,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((form.media_type) = $event)),
                mandatory: "",
                divided: "",
                color: "primary",
                variant: "outlined",
                class: "type-toggle"
              }, {
                default: _withCtx$1(() => [
                  _createVNode$1(_component_VBtn, { value: "movie" }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_VIcon, {
                        icon: "mdi-movie-outline",
                        class: "me-2"
                      }),
                      _cache[8] || (_cache[8] = _createTextVNode$1("电影", -1))
                    ]),
                    _: 1
                  }),
                  _createVNode$1(_component_VBtn, { value: "tv" }, {
                    default: _withCtx$1(() => [
                      _createVNode$1(_component_VIcon, {
                        icon: "mdi-television-classic",
                        class: "me-2"
                      }),
                      _cache[9] || (_cache[9] = _createTextVNode$1("电视剧", -1))
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }, 8, ["modelValue"]),
              _createVNode$1(_component_VTextField, {
                modelValue: form.tmdb_id,
                "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((form.tmdb_id) = $event)),
                type: "number",
                min: "1",
                label: "TMDB ID",
                "prepend-inner-icon": "mdi-database-search-outline",
                "hide-details": "auto"
              }, null, 8, ["modelValue"]),
              (form.media_type === 'tv')
                ? (_openBlock$1(), _createBlock$1(_component_VTextField, {
                    key: 0,
                    modelValue: form.season,
                    "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((form.season) = $event)),
                    type: "number",
                    min: "0",
                    label: "季号",
                    "prepend-inner-icon": "mdi-format-list-numbered",
                    hint: "特别篇填写 0",
                    "persistent-hint": ""
                  }, null, 8, ["modelValue"]))
                : _createCommentVNode$1("", true),
              _createVNode$1(_component_VSelect, {
                modelValue: form.category,
                "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((form.category) = $event)),
                items: categoryItems.value,
                label: "分类",
                "prepend-inner-icon": "mdi-folder-outline",
                "hide-details": "auto"
              }, null, 8, ["modelValue", "items"]),
              _createElementVNode$1("div", _hoisted_2$1, [
                _cache[10] || (_cache[10] = _createElementVNode$1("span", null, "MoviePilot 自动分类", -1)),
                _createElementVNode$1("strong", null, _toDisplayString$1(automaticCategory.value), 1)
              ])
            ]),
            _: 1
          }),
          _createVNode$1(_component_VDivider),
          _createVNode$1(_component_VCardActions, { class: "dialog-actions" }, {
            default: _withCtx$1(() => [
              _createVNode$1(_component_VBtn, {
                variant: "text",
                disabled: __props.loading,
                onClick: _cache[5] || (_cache[5] = $event => (open.value = false))
              }, {
                default: _withCtx$1(() => [...(_cache[11] || (_cache[11] = [
                  _createTextVNode$1("取消", -1)
                ]))]),
                _: 1
              }, 8, ["disabled"]),
              _createVNode$1(_component_VBtn, {
                color: "primary",
                variant: "flat",
                "prepend-icon": "mdi-check",
                loading: __props.loading,
                disabled: !Number(form.tmdb_id || 0),
                onClick: submit
              }, {
                default: _withCtx$1(() => [...(_cache[12] || (_cache[12] = [
                  _createTextVNode$1(" 重新识别 ", -1)
                ]))]),
                _: 1
              }, 8, ["loading", "disabled"])
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["modelValue"]))
}
}

};
const ManualIdentifyDialog = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-3e83c70b"]]);

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
const _hoisted_10 = {
  key: 0,
  class: "selection-bar"
};
const _hoisted_11 = {
  key: 0,
  class: "selection-actions"
};
const _hoisted_12 = {
  key: 1,
  class: "selection-actions"
};
const _hoisted_13 = {
  key: 1,
  class: "poster-grid"
};
const _hoisted_14 = { key: 2 };
const _hoisted_15 = { class: "qb-toolbar" };
const _hoisted_16 = { class: "text-caption text-medium-emphasis" };
const _hoisted_17 = { class: "qb-task-line" };
const _hoisted_18 = {
  key: 1,
  class: "text-caption mt-1 text-truncate"
};
const _hoisted_19 = {
  key: 1,
  class: "selection-bar"
};
const _hoisted_20 = {
  key: 2,
  class: "poster-grid"
};
const _hoisted_21 = { key: 3 };
const _hoisted_22 = { key: 4 };
const _hoisted_23 = { class: "section-count" };
const _hoisted_24 = { class: "rss-test-summary" };
const _hoisted_25 = {
  key: 0,
  class: "rss-feed-title"
};
const _hoisted_26 = { class: "rss-feed-url" };
const _hoisted_27 = { class: "url-cell" };
const _hoisted_28 = { class: "url-cell" };

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
const categoryOptions = ref([]);
const selectedKeys = ref([]);
const itemBusyKey = ref('');
const batchAction = ref('');
const identifyDialog = ref(false);
const identifyItem = ref(null);
const mediaState = ref('');
const mediaType = ref('');
const mediaRssTaskIds = ref([]);
const qbDownloaders = ref([]);
const qbDownloader = ref('');
const qbView = ref('');
const qbKeyword = ref('');
const qbTask = ref(null);
const rssTestingTaskId = ref('');
const rssRunningTaskId = ref('');
const rssBackgroundTask = ref(null);
const rssControlLoading = ref(false);
const rssTestDialog = ref(false);
const rssTestResult = ref(null);
let qbPollTimer = null;
let rssPollTimer = null;

const tabs = [
  { title: '总览', value: 'overview', icon: 'mdi-view-dashboard-outline' },
  { title: '入库管理', value: 'library', icon: 'mdi-database-import-outline' },
  { title: 'QB 管理', value: 'qb', icon: 'mdi-download-box-outline' },
  { title: 'VT+', value: 'vt', icon: 'mdi-rss-box' },
  { title: '后台任务', value: 'tasks', icon: 'mdi-progress-clock' },
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
const rssEnabled = computed(() => overview.value.plugin?.rss_enabled !== false);
const rssTaskFilterOptions = computed(() => (rssTasks.value || []).map(task => ({
  title: task.name || task.id,
  value: String(task.id || ''),
})).filter(item => item.value));
const selectedItems = computed(() => rows.value.filter(
  item => selectedKeys.value.includes(itemKey(item)),
));
const selectedStates = computed(() => selectedItems.value.map(item => item.state || ''));
const selectionAllImported = computed(() => (
  selectedItems.value.length > 0
  && selectedStates.value.every(state => state === 'imported')
));
const selectionCanQueue = computed(() => (
  selectedItems.value.length > 0
  && selectedStates.value.every(state => ['identified', 'rolled_back'].includes(state))
));
const selectionCanImport = computed(() => (
  selectedItems.value.length > 0
  && selectedStates.value.every(state => ['identified', 'pending', 'rolled_back'].includes(state))
));
const selectionCanDeleteSource = computed(() => (
  selectedItems.value.length > 0
  && selectedStates.value.every(state => state !== 'imported')
));
const qbProgress = computed(() => {
  const processed = Number(qbTask.value?.processed || 0);
  const taskTotal = Number(qbTask.value?.total || 0);
  return taskTotal > 0 ? Math.round((processed / taskTotal) * 100) : 0
});

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

function itemKey(item) {
  return item.row_key || item.id || `${item.downloader_id}:${item.info_hash}`
}

function toggleSelected(item) {
  const key = itemKey(item);
  selectedKeys.value = selectedKeys.value.includes(key)
    ? selectedKeys.value.filter(value => value !== key)
    : [...selectedKeys.value, key];
}

function selectAllVisible() {
  selectedKeys.value = rows.value.map(itemKey);
}

function clearSelection() {
  selectedKeys.value = [];
}

async function reloadForFilter() {
  clearSelection();
  await loadActive();
}

async function loadCategories() {
  const response = unwrap(await props.api.get('plugin/RssAllInOne/categories'));
  categoryOptions.value = response?.items || [];
}

async function loadOverview() {
  const response = unwrap(await props.api.get('plugin/RssAllInOne/overview'));
  overview.value = response || overview.value;
  if (response?.qb_task?.id && !qbTask.value?.id) {
    qbTask.value = response.qb_task;
    scheduleQbPoll(response.qb_task.id);
  }
  if (response?.rss_task?.id && !rssBackgroundTask.value?.id) {
    rssBackgroundTask.value = response.rss_task;
    scheduleRssPoll(response.rss_task.id);
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

async function loadRssTasks() {
  const response = unwrap(await props.api.get('plugin/RssAllInOne/rss/tasks', {
    params: { offset: 0, limit: 100 },
  }));
  rssTasks.value = response?.items || [];
  return response
}

async function loadActive() {
  loading.value = true;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    await loadOverview();
    if (['library', 'qb'].includes(activeTab.value)) {
      await loadCategories();
    }
    if (activeTab.value === 'library') {
      await loadRssTasks();
    }
    if (activeTab.value === 'overview') {
      rows.value = [];
      total.value = 0;
      return
    }

    if (activeTab.value === 'vt' && vtTab.value === 'rss_tasks') {
      const [response] = await Promise.all([
        loadRssTasks(),
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
        rss_task_ids: mediaRssTaskIds.value.join(','),
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
    } else if (activeTab.value === 'library') {
      rows.value = items.map(item => ({
        ...item,
        row_key: item.id,
        poster: item.poster || item.details?.media?.poster_path || '',
        inventory_state: item.details?.inventory?.folder_status === 'exists'
          ? (Number(item.details?.inventory?.missing_count || 0) ? 'partial' : 'exists')
          : item.details?.inventory?.folder_status || 'missing',
        recognition_state: item.state === 'unidentified' ? 'unidentified' : 'identified',
      }));
    } else if (activeTab.value === 'qb') {
      rows.value = items.map(item => {
        const recognition = torrentRecognition(item);
        const mappings = item.details?.file_mappings || [];
        const pendingMappings = mappings.filter(mapping => !mapping.inventory_exists).length;
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

async function controlRss(enabled) {
  rssControlLoading.value = true;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/rss/control', { enabled }),
    );
    if (!response?.success) throw new Error(response?.message || 'RSS 调度开关保存失败')
    overview.value.plugin = {
      ...(overview.value.plugin || {}),
      rss_enabled: Boolean(response.enabled),
    };
    successMessage.value = response.message || 'RSS 调度状态已更新';
  } catch (error) {
    errorMessage.value = error?.message || 'RSS 调度开关保存失败';
  } finally {
    rssControlLoading.value = false;
  }
}

async function runRssTask(task) {
  const configuredTaskId = String(task?.id || '');
  rssRunningTaskId.value = configuredTaskId;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/rss/run', { task_id: configuredTaskId }),
    );
    if (!response?.success || !response?.task_id) {
      throw new Error(response?.message || 'RSS 执行启动失败')
    }
    rssBackgroundTask.value = {
      id: response.task_id,
      state: 'running',
      processed: 0,
      total: 0,
    };
    successMessage.value = response.message || 'RSS 执行已启动';
    scheduleRssPoll(response.task_id);
  } catch (error) {
    rssRunningTaskId.value = '';
    errorMessage.value = error?.message || 'RSS 执行启动失败';
  }
}

function scheduleRssPoll(taskId) {
  if (!taskId) return
  window.clearTimeout(rssPollTimer);
  rssPollTimer = window.setTimeout(() => pollRssTask(taskId), 1200);
}

async function pollRssTask(taskId) {
  try {
    const response = unwrap(
      await props.api.get(`plugin/RssAllInOne/tasks/${taskId}`),
    );
    if (!response?.success || !response?.task) return
    rssBackgroundTask.value = response.task;
    if (['queued', 'running'].includes(response.task.state)) {
      scheduleRssPoll(taskId);
      return
    }
    const result = response.task.result || {};
    successMessage.value = response.task.state === 'succeeded'
      ? `RSS 执行完成：加入 ${result.queued || 0}，已存在 ${result.existing || 0}，来源重复 ${result.duplicate_source || 0}，失败 ${result.failed || 0}`
      : `RSS 执行已${response.task.state === 'cancelled' ? '停止' : '结束'}`;
    rssRunningTaskId.value = '';
    await loadOverview();
  } catch (error) {
    rssRunningTaskId.value = '';
    errorMessage.value = error?.message || '读取 RSS 执行进度失败';
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

function openIdentify(item) {
  identifyItem.value = item;
  identifyDialog.value = true;
}

async function refreshItem(item) {
  const key = itemKey(item);
  if (activeTab.value === 'library' && !item.id) {
    errorMessage.value = '该记录缺少媒体 ID，暂时无法刷新';
    return
  }
  if (activeTab.value !== 'library' && (!item.downloader_id || !item.info_hash)) {
    errorMessage.value = '该记录没有关联的 qB 任务，暂时无法重新识别';
    return
  }
  itemBusyKey.value = key;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    const response = activeTab.value === 'library'
      ? unwrap(await props.api.post('plugin/RssAllInOne/media/refresh', {
        media_id: item.id,
      }))
      : unwrap(await props.api.post('plugin/RssAllInOne/qb/item/refresh', {
        downloader_id: item.downloader_id,
        info_hash: item.info_hash,
      }));
    if (!response?.success) throw new Error(response?.message || '刷新失败')
    successMessage.value = response.message || '任务已刷新';
    await loadActive();
  } catch (error) {
    errorMessage.value = error?.message || '刷新失败';
  } finally {
    itemBusyKey.value = '';
  }
}

async function saveManualIdentify(payload) {
  const key = itemKey(identifyItem.value || payload);
  itemBusyKey.value = key;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/qb/item/identify', payload),
    );
    if (!response?.success) throw new Error(response?.message || '人工识别失败')
    identifyDialog.value = false;
    identifyItem.value = null;
    successMessage.value = response.message || '已按指定信息重新识别';
    await loadActive();
  } catch (error) {
    errorMessage.value = error?.message || '人工识别失败';
  } finally {
    itemBusyKey.value = '';
  }
}

async function deleteMediaRecord(item) {
  if (!window.confirm(`只删除插件记录“${item.title || item.source_name || ''}”？`)) return
  itemBusyKey.value = itemKey(item);
  errorMessage.value = '';
  successMessage.value = '';
  try {
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/media/delete', { media_id: item.id }),
    );
    if (!response?.success) throw new Error(response?.message || '删除记录失败')
    successMessage.value = response.message || '媒体记录已删除';
    selectedKeys.value = selectedKeys.value.filter(value => value !== itemKey(item));
    await loadActive();
  } catch (error) {
    errorMessage.value = error?.message || '删除记录失败';
  } finally {
    itemBusyKey.value = '';
  }
}

const mediaActionLabels = {
  queue_import: '转待入库',
  import: '入库',
  delete_source: '删源',
  delete_hardlinks: '只删硬链接',
  delete_both: '删除硬链接和源文件',
};

async function runMediaAction(action) {
  if (!selectedItems.value.length || batchAction.value) return
  const label = mediaActionLabels[action] || action;
  const destructive = ['delete_source', 'delete_hardlinks', 'delete_both'].includes(action);
  if (destructive) {
    const warning = action === 'delete_source'
      ? '将删除选中卡片持久化映射中的源文件，并移除插件记录；不会删除硬链接。'
      : action === 'delete_hardlinks'
        ? '只删除本插件实际创建的硬链接；库存已存在或非插件创建的目标会保留。项目将回退到识别列表。'
        : '将删除本插件实际创建的硬链接和映射中的源文件，并移除插件记录。此操作不可恢复。';
    if (!window.confirm(`${warning}\n\n确定对 ${selectedItems.value.length} 项执行“${label}”吗？`)) return
  }
  batchAction.value = action;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    const payload = {
      action,
      media_ids: selectedItems.value.map(item => item.id),
    };
    if (destructive) payload.confirm = `CONFIRM_${action.toUpperCase()}`;
    const response = unwrap(
      await props.api.post('plugin/RssAllInOne/media/action', payload),
    );
    if (!response?.success && !response?.partial) {
      throw new Error(response?.message || `${label}失败`)
    }
    if (response.partial) {
      const failures = (response.results || [])
        .filter(item => !item.success)
        .slice(0, 3)
        .map(item => item.message)
        .join('；');
      errorMessage.value = `${response.message}${failures ? `：${failures}` : ''}`;
    } else {
      successMessage.value = response.message || `${label}完成`;
    }
    clearSelection();
    await loadActive();
  } catch (error) {
    errorMessage.value = error?.message || `${label}失败`;
  } finally {
    batchAction.value = '';
  }
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
  clearSelection();
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
  clearSelection();
  if (activeTab.value === 'vt') loadActive();
});
watch([mediaState, mediaType, mediaRssTaskIds], () => {
  clearSelection();
  if (activeTab.value === 'library') loadActive();
});
watch([qbDownloader, qbView], () => {
  clearSelection();
  if (activeTab.value === 'qb') loadActive();
});
onMounted(loadActive);
onBeforeUnmount(() => {
  window.clearTimeout(qbPollTimer);
  window.clearTimeout(rssPollTimer);
});

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
  const _component_VEmptyState = _resolveComponent("VEmptyState");
  const _component_VProgressLinear = _resolveComponent("VProgressLinear");
  const _component_VBtnToggle = _resolveComponent("VBtnToggle");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VDataTable = _resolveComponent("VDataTable");
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
          _cache[18] || (_cache[18] = _createElementVNode("div", { class: "text-h6" }, "RSS一条龙", -1)),
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
                  _cache[19] || (_cache[19] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "媒体记录", -1)),
                  _createElementVNode("strong", null, _toDisplayString(overview.value.counts?.media || 0), 1)
                ]),
                _: 1
              }),
              _createVNode(_component_VSheet, {
                border: "",
                class: "metric-item"
              }, {
                default: _withCtx(() => [
                  _cache[20] || (_cache[20] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "qB 快照", -1)),
                  _createElementVNode("strong", null, _toDisplayString(overview.value.counts?.torrents || 0), 1)
                ]),
                _: 1
              }),
              _createVNode(_component_VSheet, {
                border: "",
                class: "metric-item"
              }, {
                default: _withCtx(() => [
                  _cache[21] || (_cache[21] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "RSS 历史", -1)),
                  _createElementVNode("strong", null, _toDisplayString(overview.value.counts?.rss_history || 0), 1)
                ]),
                _: 1
              }),
              _createVNode(_component_VSheet, {
                border: "",
                class: "metric-item"
              }, {
                default: _withCtx(() => [
                  _cache[22] || (_cache[22] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "后台任务", -1)),
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
                _cache[23] || (_cache[23] = _createElementVNode("thead", null, [
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
              { title: '已识别', value: 'identified' },
              { title: '未识别', value: 'unidentified' },
              { title: '已存在', value: 'existing' },
              { title: '待入库', value: 'pending' },
              { title: '已入库', value: 'imported' },
              { title: '已回退', value: 'rolled_back' },
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
                _createVNode(_component_VSelect, {
                  modelValue: mediaRssTaskIds.value,
                  "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((mediaRssTaskIds).value = $event)),
                  items: rssTaskFilterOptions.value,
                  label: "RSS任务",
                  multiple: "",
                  chips: "",
                  "closable-chips": "",
                  clearable: "",
                  density: "compact",
                  "hide-details": "",
                  class: "rss-task-filter"
                }, null, 8, ["modelValue", "items"]),
                _createElementVNode("span", _hoisted_9, _toDisplayString(total.value) + " 项", 1)
              ]),
              (rows.value.length)
                ? (_openBlock(), _createElementBlock("div", _hoisted_10, [
                    _createElementVNode("span", null, "已选 " + _toDisplayString(selectedKeys.value.length) + " 项", 1),
                    _createVNode(_component_VBtn, {
                      size: "small",
                      variant: "text",
                      onClick: selectAllVisible
                    }, {
                      default: _withCtx(() => [...(_cache[24] || (_cache[24] = [
                        _createTextVNode("全选当前", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_VBtn, {
                      size: "small",
                      variant: "text",
                      disabled: !selectedKeys.value.length,
                      onClick: _cache[4] || (_cache[4] = $event => (selectedKeys.value = []))
                    }, {
                      default: _withCtx(() => [...(_cache[25] || (_cache[25] = [
                        _createTextVNode("取消选择", -1)
                      ]))]),
                      _: 1
                    }, 8, ["disabled"]),
                    _createVNode(_component_VSpacer),
                    (!selectionAllImported.value)
                      ? (_openBlock(), _createElementBlock("div", _hoisted_11, [
                          _createVNode(_component_VBtn, {
                            size: "small",
                            variant: "tonal",
                            color: "purple",
                            "prepend-icon": "mdi-tray-arrow-down",
                            disabled: !selectionCanQueue.value || Boolean(batchAction.value),
                            loading: batchAction.value === 'queue_import',
                            onClick: _cache[5] || (_cache[5] = $event => (runMediaAction('queue_import')))
                          }, {
                            default: _withCtx(() => [...(_cache[26] || (_cache[26] = [
                              _createTextVNode("转待入库", -1)
                            ]))]),
                            _: 1
                          }, 8, ["disabled", "loading"]),
                          _createVNode(_component_VBtn, {
                            size: "small",
                            variant: "tonal",
                            color: "primary",
                            "prepend-icon": "mdi-link-variant-plus",
                            disabled: !selectionCanImport.value || Boolean(batchAction.value),
                            loading: batchAction.value === 'import',
                            onClick: _cache[6] || (_cache[6] = $event => (runMediaAction('import')))
                          }, {
                            default: _withCtx(() => [...(_cache[27] || (_cache[27] = [
                              _createTextVNode("入库", -1)
                            ]))]),
                            _: 1
                          }, 8, ["disabled", "loading"]),
                          _createVNode(_component_VBtn, {
                            size: "small",
                            variant: "tonal",
                            color: "error",
                            "prepend-icon": "mdi-delete-alert-outline",
                            disabled: !selectionCanDeleteSource.value || Boolean(batchAction.value),
                            loading: batchAction.value === 'delete_source',
                            onClick: _cache[7] || (_cache[7] = $event => (runMediaAction('delete_source')))
                          }, {
                            default: _withCtx(() => [...(_cache[28] || (_cache[28] = [
                              _createTextVNode("删源", -1)
                            ]))]),
                            _: 1
                          }, 8, ["disabled", "loading"])
                        ]))
                      : (_openBlock(), _createElementBlock("div", _hoisted_12, [
                          _createVNode(_component_VBtn, {
                            size: "small",
                            variant: "tonal",
                            color: "warning",
                            "prepend-icon": "mdi-link-variant-off",
                            disabled: Boolean(batchAction.value),
                            loading: batchAction.value === 'delete_hardlinks',
                            onClick: _cache[8] || (_cache[8] = $event => (runMediaAction('delete_hardlinks')))
                          }, {
                            default: _withCtx(() => [...(_cache[29] || (_cache[29] = [
                              _createTextVNode("只删硬链接", -1)
                            ]))]),
                            _: 1
                          }, 8, ["disabled", "loading"]),
                          _createVNode(_component_VBtn, {
                            size: "small",
                            variant: "tonal",
                            color: "error",
                            "prepend-icon": "mdi-delete-forever-outline",
                            disabled: Boolean(batchAction.value),
                            loading: batchAction.value === 'delete_both',
                            onClick: _cache[9] || (_cache[9] = $event => (runMediaAction('delete_both')))
                          }, {
                            default: _withCtx(() => [...(_cache[30] || (_cache[30] = [
                              _createTextVNode("删除硬链接和源文件", -1)
                            ]))]),
                            _: 1
                          }, 8, ["disabled", "loading"])
                        ]))
                  ]))
                : _createCommentVNode("", true),
              (rows.value.length)
                ? (_openBlock(), _createElementBlock("div", _hoisted_13, [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(rows.value, (item) => {
                      return (_openBlock(), _createBlock(MediaPosterCard, {
                        key: itemKey(item),
                        item: item,
                        mode: item.state === 'imported' ? 'imported' : 'pending',
                        selected: selectedKeys.value.includes(itemKey(item)),
                        busy: itemBusyKey.value === itemKey(item),
                        onToggle: toggleSelected,
                        onRefresh: refreshItem,
                        onEdit: openIdentify,
                        onDelete: deleteMediaRecord
                      }, null, 8, ["item", "mode", "selected", "busy"]))
                    }), 128))
                  ]))
                : (!loading.value)
                  ? (_openBlock(), _createBlock(_component_VEmptyState, {
                      key: 2,
                      icon: "mdi-movie-open-outline",
                      title: "暂无媒体记录"
                    }))
                  : _createCommentVNode("", true),
              (loading.value)
                ? (_openBlock(), _createBlock(_component_VProgressLinear, {
                    key: 3,
                    indeterminate: "",
                    color: "primary"
                  }))
                : _createCommentVNode("", true)
            ]))
          : (activeTab.value === 'qb')
            ? (_openBlock(), _createElementBlock("section", _hoisted_14, [
                _createElementVNode("div", _hoisted_15, [
                  _createVNode(_component_VSelect, {
                    modelValue: qbDownloader.value,
                    "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((qbDownloader).value = $event)),
                    items: [{ title: '全部节点', value: '' }, ...qbDownloaders.value],
                    label: "QB 节点",
                    density: "compact",
                    "hide-details": "",
                    class: "filter-control"
                  }, null, 8, ["modelValue", "items"]),
                  _createVNode(_component_VBtnToggle, {
                    modelValue: qbView.value,
                    "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((qbView).value = $event)),
                    mandatory: "",
                    divided: "",
                    density: "compact",
                    variant: "outlined",
                    color: "primary"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VBtn, { value: "" }, {
                        default: _withCtx(() => [...(_cache[31] || (_cache[31] = [
                          _createTextVNode("全部", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VBtn, { value: "existing" }, {
                        default: _withCtx(() => [...(_cache[32] || (_cache[32] = [
                          _createTextVNode("已存在", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VBtn, { value: "pending" }, {
                        default: _withCtx(() => [...(_cache[33] || (_cache[33] = [
                          _createTextVNode("待下载", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }, 8, ["modelValue"]),
                  _createVNode(_component_VTextField, {
                    modelValue: qbKeyword.value,
                    "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((qbKeyword).value = $event)),
                    label: "搜索名称或 Hash",
                    "prepend-inner-icon": "mdi-magnify",
                    density: "compact",
                    "hide-details": "",
                    clearable: "",
                    class: "qb-search",
                    onKeyup: _withKeys(reloadForFilter, ["enter"]),
                    "onClick:clear": reloadForFilter
                  }, null, 8, ["modelValue"]),
                  _createVNode(_component_VSpacer),
                  _createElementVNode("span", _hoisted_16, _toDisplayString(total.value) + " 项", 1),
                  _createVNode(_component_VBtn, {
                    color: "primary",
                    variant: "tonal",
                    "prepend-icon": "mdi-refresh",
                    loading: qbRefreshing.value,
                    disabled: qbRefreshing.value || !overview.value.plugin?.enabled,
                    onClick: refreshQb
                  }, {
                    default: _withCtx(() => [...(_cache[34] || (_cache[34] = [
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
                        _createElementVNode("div", _hoisted_17, [
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
                          ? (_openBlock(), _createElementBlock("div", _hoisted_18, _toDisplayString(qbTask.value.current_item), 1))
                          : _createCommentVNode("", true)
                      ]),
                      _: 1
                    }, 8, ["type"]))
                  : _createCommentVNode("", true),
                (rows.value.length)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_19, [
                      _createElementVNode("span", null, "已选 " + _toDisplayString(selectedKeys.value.length) + " 项", 1),
                      _createVNode(_component_VBtn, {
                        size: "small",
                        variant: "text",
                        onClick: selectAllVisible
                      }, {
                        default: _withCtx(() => [...(_cache[35] || (_cache[35] = [
                          _createTextVNode("全选当前", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VBtn, {
                        size: "small",
                        variant: "text",
                        disabled: !selectedKeys.value.length,
                        onClick: _cache[13] || (_cache[13] = $event => (selectedKeys.value = []))
                      }, {
                        default: _withCtx(() => [...(_cache[36] || (_cache[36] = [
                          _createTextVNode("取消选择", -1)
                        ]))]),
                        _: 1
                      }, 8, ["disabled"])
                    ]))
                  : _createCommentVNode("", true),
                (rows.value.length)
                  ? (_openBlock(), _createElementBlock("div", _hoisted_20, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(rows.value, (item) => {
                        return (_openBlock(), _createBlock(MediaPosterCard, {
                          key: itemKey(item),
                          item: item,
                          mode: "qb",
                          selected: selectedKeys.value.includes(itemKey(item)),
                          busy: itemBusyKey.value === itemKey(item),
                          onToggle: toggleSelected,
                          onRefresh: refreshItem,
                          onEdit: openIdentify
                        }, null, 8, ["item", "selected", "busy"]))
                      }), 128))
                    ]))
                  : (!loading.value)
                    ? (_openBlock(), _createBlock(_component_VEmptyState, {
                        key: 3,
                        icon: "mdi-download-box-outline",
                        title: "暂无 qB 任务"
                      }))
                    : _createCommentVNode("", true),
                (loading.value)
                  ? (_openBlock(), _createBlock(_component_VProgressLinear, {
                      key: 4,
                      indeterminate: "",
                      color: "primary"
                    }))
                  : _createCommentVNode("", true)
              ]))
            : (activeTab.value === 'vt')
              ? (_openBlock(), _createElementBlock("section", _hoisted_21, [
                  _createVNode(_component_VTabs, {
                    modelValue: vtTab.value,
                    "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((vtTab).value = $event)),
                    density: "compact",
                    color: "primary",
                    class: "sub-tabs"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VTab, { value: "rss_tasks" }, {
                        default: _withCtx(() => [...(_cache[37] || (_cache[37] = [
                          _createTextVNode("RSS任务", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VTab, { value: "rss_history" }, {
                        default: _withCtx(() => [...(_cache[38] || (_cache[38] = [
                          _createTextVNode("RSS历史", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_VTab, { value: "sites" }, {
                        default: _withCtx(() => [...(_cache[39] || (_cache[39] = [
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
                        "running-task-id": rssRunningTaskId.value,
                        "rss-enabled": rssEnabled.value,
                        controlling: rssControlLoading.value,
                        onSave: saveRssTasks,
                        onReload: loadActive,
                        onTest: testRssTask,
                        onRun: runRssTask,
                        onControl: controlRss
                      }, null, 8, ["items", "downloaders", "sites", "loading", "testing-task-id", "running-task-id", "rss-enabled", "controlling"]))
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
                ? (_openBlock(), _createElementBlock("section", _hoisted_22, [
                    _createElementVNode("div", _hoisted_23, _toDisplayString(total.value) + " 个后台任务", 1),
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
    _createVNode(ManualIdentifyDialog, {
      modelValue: identifyDialog.value,
      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((identifyDialog).value = $event)),
      item: identifyItem.value,
      categories: categoryOptions.value,
      loading: Boolean(itemBusyKey.value),
      onSave: saveManualIdentify
    }, null, 8, ["modelValue", "item", "categories", "loading"]),
    _createVNode(_component_VDialog, {
      modelValue: rssTestDialog.value,
      "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((rssTestDialog).value = $event)),
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
                  onClick: _cache[16] || (_cache[16] = $event => (rssTestDialog.value = false))
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
                    _createElementVNode("div", _hoisted_24, [
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
                      ? (_openBlock(), _createElementBlock("div", _hoisted_25, _toDisplayString(rssTestResult.value.feed.title), 1))
                      : _createCommentVNode("", true),
                    _createElementVNode("code", _hoisted_26, _toDisplayString(rssTestResult.value.feed?.final_url_masked), 1),
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
                        _createElementVNode("code", _hoisted_27, _toDisplayString(item.enclosure_url_masked || '-'), 1)
                      ]),
                      "item.detail_url_masked": _withCtx(({ item }) => [
                        _createElementVNode("code", _hoisted_28, _toDisplayString(item.detail_url_masked || '-'), 1)
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
const AppPage = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-d0e4fc47"]]);

export { AppPage as default };
