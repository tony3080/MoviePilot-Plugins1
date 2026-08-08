import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,mergeProps:_mergeProps,withCtx:_withCtx,createTextVNode:_createTextVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString,createBlock:_createBlock,createCommentVNode:_createCommentVNode} = await importShared('vue');


const _hoisted_1 = { class: "config-root" };
const _hoisted_2 = { class: "config-section-header" };
const _hoisted_3 = { class: "staging-root-list" };
const _hoisted_4 = {
  key: 0,
  class: "text-caption text-error"
};

const {computed,onMounted,ref} = await importShared('vue');



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
  inventory_root: '/SSD/云盘/strm/影视库',
  source_routes: defaultRoutes,
  cd2_grpc_addr: '',
  cd2_token: '',
  cd2_dest_root: '',
  pending_import_cron: '0 1 * * *',
  cd2_discovery_timeout: 180,
  cd2_card_timeout: 7200,
  cd2_poll_interval: 10,
  cd2_transfer_grace: 20,
  cd2_risk_cooldown: 1800,
  cd2_risk_retry_limit: 3,
  catchup_base_url: '',
  catchup_page_id: '',
  catchup_token: '',
  scan_base_url: '',
  scan_username: '',
  scan_password: '',
  scan_setting_name: '',
  scan_target_name: '',
  scan_callback_secret: '',
  scan_callback_server_id: '',
  scan_callback_task_id: '',
  scan_callback_task_name: '',
  scan_callback_timeout: 7200,
};

const config = ref({ ...defaults });
const section = ref('general');
const stagingRoots = computed(() => {
  const roots = [];
  for (const route of config.value.source_routes || []) {
    if (route.enabled === false) continue
    for (const value of Object.values(route.link_roots || {})) {
      const path = String(value || '').trim();
      if (path && !roots.includes(path)) roots.push(path);
    }
  }
  return roots
});

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
  next.source_routes = routes.map(normalizeRoute);
  delete next.category_groups;
  delete next.cd2_plugin_staging_root;
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
  const _component_VRow = _resolveComponent("VRow");
  const _component_VWindowItem = _resolveComponent("VWindowItem");
  const _component_VChip = _resolveComponent("VChip");
  const _component_VExpansionPanelText = _resolveComponent("VExpansionPanelText");
  const _component_VExpansionPanel = _resolveComponent("VExpansionPanel");
  const _component_VExpansionPanels = _resolveComponent("VExpansionPanels");
  const _component_VWindow = _resolveComponent("VWindow");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      density: "comfortable",
      color: "transparent"
    }, {
      default: _withCtx(() => [
        _cache[29] || (_cache[29] = _createElementVNode("div", { class: "text-h6 ms-3" }, "RSS一条龙配置", -1)),
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
          default: _withCtx(() => [...(_cache[30] || (_cache[30] = [
            _createTextVNode("常规", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_VTab, { value: "cd2" }, {
          default: _withCtx(() => [...(_cache[31] || (_cache[31] = [
            _createTextVNode("CloudDrive2", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_VTab, { value: "external" }, {
          default: _withCtx(() => [...(_cache[32] || (_cache[32] = [
            _createTextVNode("外部联动", -1)
          ]))]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VWindow, {
      modelValue: section.value,
      "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((section).value = $event)),
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
                _createVNode(_component_VCol, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.inventory_root,
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.value.inventory_root) = $event)),
                      label: "最终媒体库根目录",
                      placeholder: "/SSD/云盘/strm/影视库"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, { cols: "12" }, {
                  default: _withCtx(() => [
                    _createElementVNode("div", _hoisted_2, [
                      _cache[34] || (_cache[34] = _createElementVNode("div", { class: "text-subtitle-2" }, "源路径路由", -1)),
                      _createVNode(_component_VBtn, {
                        size: "small",
                        variant: "text",
                        "prepend-icon": "mdi-plus",
                        onClick: addRoute
                      }, {
                        default: _withCtx(() => [...(_cache[33] || (_cache[33] = [
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
                        _cache[35] || (_cache[35] = _createElementVNode("thead", null, [
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
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_VWindowItem, { value: "cd2" }, {
          default: _withCtx(() => [
            _cache[37] || (_cache[37] = _createElementVNode("div", { class: "settings-section-title" }, "CloudDrive2 连接与路径", -1)),
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.cd2_grpc_addr,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.cd2_grpc_addr) = $event)),
                      label: "CD2 gRPC 地址 *",
                      placeholder: "192.168.110.31:19798",
                      hint: "只填写 IP:端口，不包含 http://",
                      "persistent-hint": ""
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
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.cd2_token) = $event)),
                      label: "CD2 访问令牌 *",
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
                      modelValue: config.value.cd2_dest_root,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.cd2_dest_root) = $event)),
                      label: "CD2 上传任务目标根目录 *",
                      placeholder: "/115/影视库",
                      hint: "优先填 CD2 gRPC 中的云盘路径；填写本机挂载路径时会自动校正",
                      "persistent-hint": ""
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
                      modelValue: config.value.pending_import_cron,
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.value.pending_import_cron) = $event)),
                      label: "待入库 CRON *",
                      placeholder: "30 1 * * *",
                      hint: "五段 CRON；只在存在待入库卡片时启动处理",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCol, { cols: "12" }, {
                  default: _withCtx(() => [
                    _cache[36] || (_cache[36] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mb-2" }, "自动使用的本地硬链接根目录", -1)),
                    _createElementVNode("div", _hoisted_3, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(stagingRoots.value, (root) => {
                        return (_openBlock(), _createBlock(_component_VChip, {
                          key: root,
                          size: "small",
                          variant: "tonal",
                          color: "info"
                        }, {
                          default: _withCtx(() => [
                            _createTextVNode(_toDisplayString(root), 1)
                          ]),
                          _: 2
                        }, 1024))
                      }), 128)),
                      (!stagingRoots.value.length)
                        ? (_openBlock(), _createElementBlock("span", _hoisted_4, " 源路径路由中没有可用的硬链接根目录 "))
                        : _createCommentVNode("", true)
                    ])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VExpansionPanels, {
              variant: "accordion",
              class: "advanced-panels"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VExpansionPanel, { title: "CD2 高级监控参数" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VExpansionPanelText, null, {
                      default: _withCtx(() => [
                        _createVNode(_component_VRow, null, {
                          default: _withCtx(() => [
                            _createVNode(_component_VCol, {
                              cols: "12",
                              md: "4"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_VTextField, {
                                  modelValue: config.value.cd2_discovery_timeout,
                                  "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.value.cd2_discovery_timeout) = $event)),
                                  modelModifiers: { number: true },
                                  label: "上传任务发现超时（秒）",
                                  type: "number"
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
                                  modelValue: config.value.cd2_card_timeout,
                                  "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.value.cd2_card_timeout) = $event)),
                                  modelModifiers: { number: true },
                                  label: "单卡最终超时（秒）",
                                  type: "number"
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
                                  modelValue: config.value.cd2_poll_interval,
                                  "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.value.cd2_poll_interval) = $event)),
                                  modelModifiers: { number: true },
                                  label: "CD2 活跃轮询（秒）",
                                  type: "number"
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
                                  modelValue: config.value.cd2_transfer_grace,
                                  "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.value.cd2_transfer_grace) = $event)),
                                  modelModifiers: { number: true },
                                  label: "真实传输观察期（秒）",
                                  type: "number"
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
                                  modelValue: config.value.cd2_risk_cooldown,
                                  "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.value.cd2_risk_cooldown) = $event)),
                                  modelModifiers: { number: true },
                                  label: "风控暂停时间（秒）",
                                  type: "number"
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
                                  modelValue: config.value.cd2_risk_retry_limit,
                                  "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.value.cd2_risk_retry_limit) = $event)),
                                  modelModifiers: { number: true },
                                  label: "连续风控停止阈值",
                                  type: "number"
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
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }),
        _createVNode(_component_VWindowItem, { value: "external" }, {
          default: _withCtx(() => [
            _cache[38] || (_cache[38] = _createElementVNode("div", { class: "settings-section-title" }, "追更控制（Emby）", -1)),
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "5"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.catchup_base_url,
                      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((config.value.catchup_base_url) = $event)),
                      label: "追更 Emby 地址 *",
                      placeholder: "http://192.168.110.31:8096"
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
                      "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((config.value.catchup_page_id) = $event)),
                      label: "追更插件 PageId *",
                      placeholder: "63c322:Settings"
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
                      "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((config.value.catchup_token) = $event)),
                      label: "追更 Emby Token *",
                      type: "password",
                      autocomplete: "new-password"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VDivider, { class: "settings-divider" }),
            _cache[39] || (_cache[39] = _createElementVNode("div", { class: "settings-section-title" }, "外部扫库控制（SA）", -1)),
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.scan_base_url,
                      "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((config.value.scan_base_url) = $event)),
                      label: "SA 系统地址 *",
                      placeholder: "http://192.168.110.31:8095"
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
                      "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((config.value.scan_username) = $event)),
                      label: "SA 登录账号 *"
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
                      "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((config.value.scan_password) = $event)),
                      label: "SA 登录密码 *",
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
                      "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((config.value.scan_setting_name) = $event)),
                      label: "SA 扫库配置名 *",
                      placeholder: "emby_server"
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
                      "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((config.value.scan_target_name) = $event)),
                      label: "SA 扫库节点名 *",
                      hint: "必须和 SA 配置中的节点名称完全一致",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VDivider, { class: "settings-divider" }),
            _cache[40] || (_cache[40] = _createElementVNode("div", { class: "settings-section-title" }, "Emby 扫库完成回调", -1)),
            _createVNode(_component_VRow, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCol, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextField, {
                      modelValue: config.value.scan_callback_secret,
                      "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((config.value.scan_callback_secret) = $event)),
                      label: "回调密钥 *",
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
                      modelValue: config.value.scan_callback_server_id,
                      "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((config.value.scan_callback_server_id) = $event)),
                      label: "Emby 服务器 ID *",
                      hint: "用于确认回调来自本轮刷新的目标 Emby",
                      "persistent-hint": ""
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
                      modelValue: config.value.scan_callback_task_id,
                      "onUpdate:modelValue": _cache[25] || (_cache[25] = $event => ((config.value.scan_callback_task_id) = $event)),
                      label: "Emby 扫库任务 ID",
                      hint: "任务 ID 与任务名称至少填写一项；优先使用 ID",
                      "persistent-hint": ""
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
                      modelValue: config.value.scan_callback_task_name,
                      "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((config.value.scan_callback_task_name) = $event)),
                      label: "Emby 扫库任务名称",
                      hint: "任务 ID 与任务名称至少填写一项",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VExpansionPanels, {
              variant: "accordion",
              class: "advanced-panels"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VExpansionPanel, { title: "回调高级参数" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VExpansionPanelText, null, {
                      default: _withCtx(() => [
                        _createVNode(_component_VRow, null, {
                          default: _withCtx(() => [
                            _createVNode(_component_VCol, {
                              cols: "12",
                              md: "4"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_VTextField, {
                                  modelValue: config.value.scan_callback_timeout,
                                  "onUpdate:modelValue": _cache[27] || (_cache[27] = $event => ((config.value.scan_callback_timeout) = $event)),
                                  modelModifiers: { number: true },
                                  label: "扫库回调等待超时（秒）",
                                  type: "number"
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
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-c6553061"]]);

export { Config as default };
