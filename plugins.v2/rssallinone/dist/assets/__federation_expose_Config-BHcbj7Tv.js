import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,mergeProps:_mergeProps,withCtx:_withCtx,createTextVNode:_createTextVNode,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


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
  database_filename: 'rssallinone.db',
  qb_refresh_cron: '*/10 * * * *',
  inventory_library_roots: '',
  cd2_grpc_addr: '',
  cd2_token: '',
  catchup_base_url: '',
  catchup_page_id: '',
  catchup_token: '',
  scan_base_url: '',
  scan_username: '',
  scan_password: '',
  scan_setting_name: '',
  scan_target_name: '',
};

const config = ref({ ...defaults });
const section = ref('general');

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
  const _component_VTab = _resolveComponent("VTab");
  const _component_VTabs = _resolveComponent("VTabs");
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VCol = _resolveComponent("VCol");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VTextarea = _resolveComponent("VTextarea");
  const _component_VRow = _resolveComponent("VRow");
  const _component_VWindowItem = _resolveComponent("VWindowItem");
  const _component_VWindow = _resolveComponent("VWindow");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      density: "comfortable",
      color: "transparent"
    }, {
      default: _withCtx(() => [
        _cache[17] || (_cache[17] = _createElementVNode("div", { class: "text-h6 ms-3" }, "RSS一条龙配置", -1)),
        _createVNode(_component_VSpacer),
        _createVNode(_component_VTooltip, { text: "保存" }, {
          activator: _withCtx(({ props: tooltipProps }) => [
            _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
              icon: "mdi-content-save",
              variant: "text",
              color: "primary",
              "aria-label": "保存",
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
              "aria-label": "关闭",
              onClick: _cache[0] || (_cache[0] = $event => (emit('close')))
            }), null, 16)
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VDivider),
    _createVNode(_component_VTabs, {
      modelValue: section.value,
      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((section).value = $event)),
      density: "compact",
      color: "primary",
      class: "config-tabs"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VTab, { value: "general" }, {
          default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
            _createTextVNode("常规", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_VTab, { value: "cd2" }, {
          default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
            _createTextVNode("CloudDrive2", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_VTab, { value: "external" }, {
          default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
            _createTextVNode("外部联动", -1)
          ]))]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VWindow, {
      modelValue: section.value,
      "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((section).value = $event)),
      class: "config-window"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VWindowItem, { value: "general" }, {
          default: _withCtx(() => [
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSwitch, {
                      modelValue: config.value.enabled,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.value.enabled) = $event)),
                      label: "启用插件",
                      color: "primary"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "8"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.database_filename,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.value.database_filename) = $event)),
                      label: "状态数据库文件名",
                      hint: "保存在 MoviePilot 分配的插件数据目录",
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
                      modelValue: config.value.qb_refresh_cron,
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.value.qb_refresh_cron) = $event)),
                      label: "QB 只读刷新 CRON",
                      placeholder: "*/10 * * * *"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextarea, {
                      modelValue: config.value.inventory_library_roots,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.inventory_library_roots) = $event)),
                      label: "最终媒体库本地根目录",
                      placeholder: "movie => /media/Movies\ntv => /media/TV",
                      hint: "库存仅核对这些本地路径；可写 movie、tv 或省略类型，每行一个绝对路径",
                      "persistent-hint": "",
                      rows: "4",
                      "auto-grow": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_VWindowItem, { value: "cd2" }, {
          default: _withCtx(() => [
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.cd2_grpc_addr,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.cd2_grpc_addr) = $event)),
                      label: "CD2 gRPC 地址",
                      placeholder: "host:port"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.cd2_token,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.cd2_token) = $event)),
                      label: "CD2 访问令牌",
                      type: "password",
                      autocomplete: "new-password"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_VWindowItem, { value: "external" }, {
          default: _withCtx(() => [
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "5"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.catchup_base_url,
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.value.catchup_base_url) = $event)),
                      label: "追更 Emby 地址"
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
                      modelValue: config.value.catchup_page_id,
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.value.catchup_page_id) = $event)),
                      label: "追更 PageId"
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
                      modelValue: config.value.catchup_token,
                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.value.catchup_token) = $event)),
                      label: "追更 Token",
                      type: "password",
                      autocomplete: "new-password"
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
                      modelValue: config.value.scan_base_url,
                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.value.scan_base_url) = $event)),
                      label: "扫库系统地址"
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
                      modelValue: config.value.scan_username,
                      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.value.scan_username) = $event)),
                      label: "扫库账号"
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
                      modelValue: config.value.scan_password,
                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.value.scan_password) = $event)),
                      label: "扫库密码",
                      type: "password",
                      autocomplete: "new-password"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.scan_setting_name,
                      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.value.scan_setting_name) = $event)),
                      label: "扫库配置名"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.scan_target_name,
                      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((config.value.scan_target_name) = $event)),
                      label: "扫库节点名"
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
      ]),
      _: 1
    }, 8, ["modelValue"])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-5d8eba99"]]);

export { Config as default };
