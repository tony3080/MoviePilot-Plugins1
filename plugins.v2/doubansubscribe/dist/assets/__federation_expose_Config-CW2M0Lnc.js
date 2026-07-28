import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,mergeProps:_mergeProps,withCtx:_withCtx,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "config-root" };

const {onMounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['save', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const defaults = {
  enabled: false,
  onlyonce: false,
  proxy: false,
  rss_urls: 'http://192.168.110.31:9150/rsshub/hot_tv',
  maoyan_enabled: false,
  maoyan_types: ['tv', 'web'],
  maoyan_num: 10,
  cron: '0 */6 * * *',
  supplement_cron: '0 23 * * *',
  max_items: 50,
  candidate_limit: 10,
  confirmation_days: 7,
  notify_subscription: true,
  media_categories: ['domestic', 'western', 'japan_korea', 'other'],
};

const categories = [
  { title: '国产剧', value: 'domestic' },
  { title: '欧美剧', value: 'western' },
  { title: '日韩剧', value: 'japan_korea' },
  { title: '其他地区', value: 'other' },
];

const maoyanTypes = [
  { title: '电视剧热度榜', value: 'tv' },
  { title: '网剧热度榜', value: 'web' },
];

const config = ref({ ...defaults });

function save() {
  emit('save', JSON.parse(JSON.stringify(config.value)));
}

onMounted(() => {
  config.value = {
    ...defaults,
    ...JSON.parse(JSON.stringify(props.initialConfig || {})),
  };
  if (!Array.isArray(config.value.media_categories)) {
    config.value.media_categories = [...defaults.media_categories];
  }
  if (!Array.isArray(config.value.maoyan_types)) {
    config.value.maoyan_types = [...defaults.maoyan_types];
  }
});

return (_ctx, _cache) => {
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VTooltip = _resolveComponent("VTooltip");
  const _component_VToolbar = _resolveComponent("VToolbar");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VCol = _resolveComponent("VCol");
  const _component_VTextarea = _resolveComponent("VTextarea");
  const _component_VSelect = _resolveComponent("VSelect");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VRow = _resolveComponent("VRow");
  const _component_VForm = _resolveComponent("VForm");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      density: "comfortable",
      color: "transparent"
    }, {
      default: _withCtx(() => [
        _cache[15] || (_cache[15] = _createElementVNode("div", { class: "text-h6 ms-3" }, "豆瓣订阅助手配置", -1)),
        _createVNode(_component_VSpacer),
        _createVNode(_component_VTooltip, { text: "保存" }, {
          activator: _withCtx(({ props: tooltipProps }) => [
            _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
              icon: "mdi-content-save",
              variant: "text",
              color: "primary",
              onClick: save
            }), null, 16)
          ]),
          _: 1
        }),
        _createVNode(_component_VTooltip, { text: "关闭" }, {
          activator: _withCtx(({ props: tooltipProps }) => [
            _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
              icon: "mdi-close",
              variant: "text",
              onClick: _cache[0] || (_cache[0] = $event => (emit('close')))
            }), null, 16)
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VDivider),
    _createVNode(_component_VForm, { class: "config-form" }, {
      default: _withCtx(() => [
        _createVNode(_component_VRow, null, {
          default: _withCtx(() => [
            _createVNode(_component_VCol, {
              cols: "12",
              md: "3"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VSwitch, {
                  modelValue: config.value.enabled,
                  "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.value.enabled) = $event)),
                  label: "启用插件",
                  color: "primary"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, {
              cols: "12",
              md: "3"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VSwitch, {
                  modelValue: config.value.onlyonce,
                  "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.value.onlyonce) = $event)),
                  label: "立即运行一次",
                  color: "primary"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, {
              cols: "12",
              md: "3"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VSwitch, {
                  modelValue: config.value.proxy,
                  "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.value.proxy) = $event)),
                  label: "内容源使用代理",
                  color: "primary"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, {
              cols: "12",
              md: "3"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VSwitch, {
                  modelValue: config.value.notify_subscription,
                  "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.value.notify_subscription) = $event)),
                  label: "订阅成功通知",
                  color: "primary"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, { cols: "12" }, {
              default: _withCtx(() => [
                _createVNode(_component_VTextarea, {
                  modelValue: config.value.rss_urls,
                  "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.rss_urls) = $event)),
                  label: "RSS 地址（每行一个）",
                  rows: "4",
                  "auto-grow": ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, {
              cols: "12",
              md: "4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VSwitch, {
                  modelValue: config.value.maoyan_enabled,
                  "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.maoyan_enabled) = $event)),
                  label: "启用猫眼全网榜单",
                  color: "primary"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, {
              cols: "12",
              md: "5"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VSelect, {
                  modelValue: config.value.maoyan_types,
                  "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.maoyan_types) = $event)),
                  items: maoyanTypes,
                  label: "猫眼榜单",
                  multiple: "",
                  chips: "",
                  "closable-chips": "",
                  disabled: !config.value.maoyan_enabled
                }, null, 8, ["modelValue", "disabled"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, {
              cols: "12",
              md: "3"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VTextField, {
                  modelValue: config.value.maoyan_num,
                  "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.value.maoyan_num) = $event)),
                  modelModifiers: { number: true },
                  label: "每榜处理条数",
                  type: "number",
                  min: "1",
                  max: "30",
                  disabled: !config.value.maoyan_enabled
                }, null, 8, ["modelValue", "disabled"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, {
              cols: "12",
              md: "4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VTextField, {
                  modelValue: config.value.cron,
                  "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.value.cron) = $event)),
                  label: "内容源执行周期"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, {
              cols: "12",
              md: "4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VTextField, {
                  modelValue: config.value.supplement_cron,
                  "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.value.supplement_cron) = $event)),
                  label: "订阅补齐执行周期",
                  hint: "每日 08:00 建立快照，到此周期检查订阅进度",
                  "persistent-hint": ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, {
              cols: "12",
              md: "4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VTextField, {
                  modelValue: config.value.max_items,
                  "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.value.max_items) = $event)),
                  modelModifiers: { number: true },
                  label: "每个 RSS 最大条目数",
                  type: "number",
                  min: "1",
                  max: "200"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, {
              cols: "12",
              md: "4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VTextField, {
                  modelValue: config.value.candidate_limit,
                  "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.value.candidate_limit) = $event)),
                  modelModifiers: { number: true },
                  label: "TMDB 候选详情上限",
                  type: "number",
                  min: "1",
                  max: "30"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, {
              cols: "12",
              md: "4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VTextField, {
                  modelValue: config.value.confirmation_days,
                  "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.value.confirmation_days) = $event)),
                  modelModifiers: { number: true },
                  label: "完成后二次确认天数",
                  type: "number",
                  min: "1",
                  max: "365"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, { cols: "12" }, {
              default: _withCtx(() => [
                _createVNode(_component_VSelect, {
                  modelValue: config.value.media_categories,
                  "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.value.media_categories) = $event)),
                  items: categories,
                  label: "需要订阅的剧集类型",
                  multiple: "",
                  chips: "",
                  "closable-chips": ""
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    })
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-4b2b8e32"]]);

export { Config as default };
