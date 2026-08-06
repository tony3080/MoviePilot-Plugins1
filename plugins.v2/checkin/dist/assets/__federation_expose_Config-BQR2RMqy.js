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
const showSmzdmCookie = ref(false);
const showChiphellCookie = ref(false);

const defaults = {
  enabled: false,
  onlyonce: false,
  notify: true,
  history_days: 30,
  smzdm_enabled: false,
  smzdm_cookie: '',
  smzdm_cron: '0 9 * * *',
  chiphell_enabled: false,
  chiphell_cookie: '',
  chiphell_cron: '10 9 * * *',
};

const config = ref({ ...defaults });

function save() {
  emit('save', JSON.parse(JSON.stringify(config.value)));
}

onMounted(() => {
  config.value = {
    ...defaults,
    ...JSON.parse(JSON.stringify(props.initialConfig || {})),
  };
});

return (_ctx, _cache) => {
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VTooltip = _resolveComponent("VTooltip");
  const _component_VToolbar = _resolveComponent("VToolbar");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VCol = _resolveComponent("VCol");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VRow = _resolveComponent("VRow");
  const _component_VForm = _resolveComponent("VForm");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      density: "comfortable",
      color: "transparent"
    }, {
      default: _withCtx(() => [
        _cache[13] || (_cache[13] = _createElementVNode("div", { class: "text-h6 ms-3" }, "签到助手配置", -1)),
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
                  modelValue: config.value.notify,
                  "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.value.notify) = $event)),
                  label: "发送结果通知",
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
                _createVNode(_component_VTextField, {
                  modelValue: config.value.history_days,
                  "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.value.history_days) = $event)),
                  modelModifiers: { number: true },
                  label: "历史保留天数",
                  type: "number",
                  min: "1",
                  max: "365"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _cache[14] || (_cache[14] = _createElementVNode("div", { class: "section-title" }, "什么值得买", -1)),
        _createVNode(_component_VRow, null, {
          default: _withCtx(() => [
            _createVNode(_component_VCol, {
              cols: "12",
              md: "4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VSwitch, {
                  modelValue: config.value.smzdm_enabled,
                  "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.smzdm_enabled) = $event)),
                  label: "启用定时签到",
                  color: "primary"
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
                  modelValue: config.value.smzdm_cron,
                  "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.smzdm_cron) = $event)),
                  label: "执行周期"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, { cols: "12" }, {
              default: _withCtx(() => [
                _createVNode(_component_VTextField, {
                  modelValue: config.value.smzdm_cookie,
                  "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.smzdm_cookie) = $event)),
                  label: "登录 Cookie",
                  type: showSmzdmCookie.value ? 'text' : 'password',
                  autocomplete: "off",
                  "append-inner-icon": showSmzdmCookie.value ? 'mdi-eye-off-outline' : 'mdi-eye-outline',
                  "onClick:appendInner": _cache[8] || (_cache[8] = $event => (showSmzdmCookie.value = !showSmzdmCookie.value))
                }, null, 8, ["modelValue", "type", "append-inner-icon"])
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_VDivider, { class: "section-divider" }),
        _cache[15] || (_cache[15] = _createElementVNode("div", { class: "section-title" }, "Chiphell", -1)),
        _createVNode(_component_VRow, null, {
          default: _withCtx(() => [
            _createVNode(_component_VCol, {
              cols: "12",
              md: "4"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VSwitch, {
                  modelValue: config.value.chiphell_enabled,
                  "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.value.chiphell_enabled) = $event)),
                  label: "启用定时保活",
                  color: "primary"
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
                  modelValue: config.value.chiphell_cron,
                  "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.value.chiphell_cron) = $event)),
                  label: "执行周期"
                }, null, 8, ["modelValue"])
              ]),
              _: 1
            }),
            _createVNode(_component_VCol, { cols: "12" }, {
              default: _withCtx(() => [
                _createVNode(_component_VTextField, {
                  modelValue: config.value.chiphell_cookie,
                  "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.value.chiphell_cookie) = $event)),
                  label: "登录 Cookie",
                  type: showChiphellCookie.value ? 'text' : 'password',
                  autocomplete: "off",
                  "append-inner-icon": showChiphellCookie.value ? 'mdi-eye-off-outline' : 'mdi-eye-outline',
                  "onClick:appendInner": _cache[12] || (_cache[12] = $event => (showChiphellCookie.value = !showChiphellCookie.value))
                }, null, 8, ["modelValue", "type", "append-inner-icon"])
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
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-e86cd7af"]]);

export { Config as default };
