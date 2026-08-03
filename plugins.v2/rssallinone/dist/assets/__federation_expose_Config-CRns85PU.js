import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,mergeProps:_mergeProps,withCtx:_withCtx,createTextVNode:_createTextVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "config-root" };
const _hoisted_2 = { class: "config-section-header" };

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

const defaultRoutes = [
  {
    name: 'UP',
    prefix: '/MP',
    link_roots: {
      movie: '/MP/电影UP',
      series: '/MP/剧集UP',
      default: '',
    },
    enabled: true,
  },
  {
    name: 'SSD',
    prefix: '/SSD',
    link_roots: {
      movie: '',
      series: '',
      default: '/SSD/云盘/l',
    },
    enabled: true,
  },
];

const defaults = {
  enabled: false,
  database_filename: 'rssallinone.db',
  qb_refresh_cron: '*/10 * * * *',
  inventory_root: '/SSD/云盘/strm/影视库',
  source_routes: defaultRoutes,
  category_groups: {
    movie: ['演唱会', '动画电影', '华语电影', '外语电影'],
    series: ['儿童剧', '动漫', '国产剧', '日韩剧', '欧美剧', '纪录片', '综艺'],
  },
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

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function parseStructured(value, fallback) {
  if (typeof value !== 'string') return value ?? fallback
  try {
    return JSON.parse(value)
  } catch {
    return fallback
  }
}

function normalizeRoute(route = {}, index = 0) {
  return {
    name: route.name || `路由${index + 1}`,
    prefix: route.prefix || '',
    link_roots: {
      movie: route.link_roots?.movie || '',
      series: route.link_roots?.series || '',
      default: route.link_roots?.default || '',
    },
    enabled: route.enabled !== false,
  }
}

function normalizeConfig(initial = {}) {
  const next = {
    ...clone(defaults),
    ...clone(initial),
  };
  const routeValue = parseStructured(initial.source_routes, defaultRoutes);
  const routes = Array.isArray(routeValue) ? routeValue : defaultRoutes;
  const groupValue = parseStructured(initial.category_groups, defaults.category_groups);
  const groups = groupValue && typeof groupValue === 'object'
    ? groupValue
    : defaults.category_groups;
  next.source_routes = routes.map(normalizeRoute);
  next.category_groups = {
    movie: Array.isArray(groups.movie)
      ? [...groups.movie]
      : [...defaults.category_groups.movie],
    series: Array.isArray(groups.series)
      ? [...groups.series]
      : [...defaults.category_groups.series],
  };
  return next
}

function save() {
  emit('save', clone(config.value));
}

function addRoute() {
  config.value.source_routes.push(normalizeRoute({}, config.value.source_routes.length));
}

function removeRoute(index) {
  config.value.source_routes.splice(index, 1);
}

onMounted(() => {
  config.value = normalizeConfig(props.initialConfig || {});
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
  const _component_VTable = _resolveComponent("VTable");
  const _component_VCombobox = _resolveComponent("VCombobox");
  const _component_VRow = _resolveComponent("VRow");
  const _component_VWindowItem = _resolveComponent("VWindowItem");
  const _component_VWindow = _resolveComponent("VWindow");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      density: "comfortable",
      color: "transparent"
    }, {
      default: _withCtx(() => [
        _cache[19] || (_cache[19] = _createElementVNode("div", { class: "text-h6 ms-3" }, "RSS一条龙配置", -1)),
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
          default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
            _createTextVNode("常规", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_VTab, { value: "cd2" }, {
          default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
            _createTextVNode("CloudDrive2", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_VTab, { value: "external" }, {
          default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
            _createTextVNode("外部联动", -1)
          ]))]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VWindow, {
      modelValue: section.value,
      "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((section).value = $event)),
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
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "8"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.inventory_root,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.inventory_root) = $event)),
                      label: "最终媒体库根目录",
                      placeholder: "/SSD/云盘/strm/影视库"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createElementVNode("div", _hoisted_2, [
                      _cache[24] || (_cache[24] = _createElementVNode("div", { class: "text-subtitle-2" }, "源路径路由", -1)),
                      _createVNode(_component_VBtn, {
                        size: "small",
                        variant: "text",
                        "prepend-icon": "mdi-plus",
                        onClick: addRoute
                      }, {
                        default: _withCtx(() => [...(_cache[23] || (_cache[23] = [
                          _createTextVNode(" 添加路由 ", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _createVNode(_component_VTable, {
                      density: "compact",
                      class: "route-table"
                    }, {
                      default: _withCtx(() => [
                        _cache[25] || (_cache[25] = _createElementVNode("thead", null, [
                          _createElementVNode("tr", null, [
                            _createElementVNode("th", null, "启用"),
                            _createElementVNode("th", null, "名称"),
                            _createElementVNode("th", null, "源路径前缀"),
                            _createElementVNode("th", null, "电影硬链接根目录"),
                            _createElementVNode("th", null, "剧集硬链接根目录"),
                            _createElementVNode("th", null, "默认硬链接根目录"),
                            _createElementVNode("th")
                          ])
                        ], -1)),
                        _createElementVNode("tbody", null, [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(config.value.source_routes, (route, index) => {
                            return (_openBlock(), _createElementBlock("tr", {
                              key: `${route.name}-${index}`
                            }, [
                              _createElementVNode("td", null, [
                                _createVNode(_component_VSwitch, {
                                  modelValue: route.enabled,
                                  "onUpdate:modelValue": $event => ((route.enabled) = $event),
                                  density: "compact",
                                  "hide-details": ""
                                }, null, 8, ["modelValue", "onUpdate:modelValue"])
                              ]),
                              _createElementVNode("td", null, [
                                _createVNode(_component_VTextField, {
                                  modelValue: route.name,
                                  "onUpdate:modelValue": $event => ((route.name) = $event),
                                  density: "compact",
                                  "hide-details": ""
                                }, null, 8, ["modelValue", "onUpdate:modelValue"])
                              ]),
                              _createElementVNode("td", null, [
                                _createVNode(_component_VTextField, {
                                  modelValue: route.prefix,
                                  "onUpdate:modelValue": $event => ((route.prefix) = $event),
                                  density: "compact",
                                  "hide-details": ""
                                }, null, 8, ["modelValue", "onUpdate:modelValue"])
                              ]),
                              _createElementVNode("td", null, [
                                _createVNode(_component_VTextField, {
                                  modelValue: route.link_roots.movie,
                                  "onUpdate:modelValue": $event => ((route.link_roots.movie) = $event),
                                  density: "compact",
                                  "hide-details": ""
                                }, null, 8, ["modelValue", "onUpdate:modelValue"])
                              ]),
                              _createElementVNode("td", null, [
                                _createVNode(_component_VTextField, {
                                  modelValue: route.link_roots.series,
                                  "onUpdate:modelValue": $event => ((route.link_roots.series) = $event),
                                  density: "compact",
                                  "hide-details": ""
                                }, null, 8, ["modelValue", "onUpdate:modelValue"])
                              ]),
                              _createElementVNode("td", null, [
                                _createVNode(_component_VTextField, {
                                  modelValue: route.link_roots.default,
                                  "onUpdate:modelValue": $event => ((route.link_roots.default) = $event),
                                  density: "compact",
                                  "hide-details": ""
                                }, null, 8, ["modelValue", "onUpdate:modelValue"])
                              ]),
                              _createElementVNode("td", null, [
                                _createVNode(_component_VTooltip, { text: "删除路由" }, {
                                  activator: _withCtx(({ props: tooltipProps }) => [
                                    _createVNode(_component_VBtn, _mergeProps({ ref_for: true }, tooltipProps, {
                                      icon: "mdi-delete-outline",
                                      size: "small",
                                      variant: "text",
                                      color: "error",
                                      "aria-label": "删除路由",
                                      onClick: $event => (removeRoute(index))
                                    }), null, 16, ["onClick"])
                                  ]),
                                  _: 2
                                }, 1024)
                              ])
                            ]))
                          }), 128))
                        ])
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VCombobox, {
                      modelValue: config.value.category_groups.movie,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.category_groups.movie) = $event)),
                      label: "电影目录组分类",
                      multiple: "",
                      chips: "",
                      "closable-chips": "",
                      "hide-selected": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VCombobox, {
                      modelValue: config.value.category_groups.series,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.category_groups.series) = $event)),
                      label: "剧集目录组分类",
                      multiple: "",
                      chips: "",
                      "closable-chips": "",
                      "hide-selected": ""
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
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.value.cd2_grpc_addr) = $event)),
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
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.value.cd2_token) = $event)),
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
                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.value.catchup_base_url) = $event)),
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
                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.value.catchup_page_id) = $event)),
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
                      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.value.catchup_token) = $event)),
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
                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.value.scan_base_url) = $event)),
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
                      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.value.scan_username) = $event)),
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
                      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((config.value.scan_password) = $event)),
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
                      "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((config.value.scan_setting_name) = $event)),
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
                      "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((config.value.scan_target_name) = $event)),
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
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-1b079789"]]);

export { Config as default };
