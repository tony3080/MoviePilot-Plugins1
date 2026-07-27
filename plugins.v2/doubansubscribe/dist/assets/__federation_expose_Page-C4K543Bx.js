import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,mergeProps:_mergeProps,withCtx:_withCtx,createTextVNode:_createTextVNode,withKeys:_withKeys,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString,createCommentVNode:_createCommentVNode,createBlock:_createBlock} = await importShared('vue');


const _hoisted_1 = { class: "page-root" };
const _hoisted_2 = { class: "history-tools" };
const _hoisted_3 = { class: "search-row" };
const _hoisted_4 = { class: "filter-row" };
const _hoisted_5 = { class: "text-body-2 text-medium-emphasis result-count" };
const _hoisted_6 = { class: "title-cell" };
const _hoisted_7 = {
  key: 0,
  class: "text-caption text-medium-emphasis"
};
const _hoisted_8 = { class: "row-actions" };
const _hoisted_9 = { class: "text-subtitle-1 ms-4 diagnostics-title" };
const _hoisted_10 = { class: "error-cell" };

const {computed,onMounted,ref,watch} = await importShared('vue');



const _sfc_main = {
  __name: 'Page',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['close'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const activeTab = ref('history');
const loading = ref(false);
const running = ref(false);
const rows = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(25);
const keywordInput = ref('');
const keyword = ref('');
const group = ref('all');
const category = ref('');
const retrying = ref(new Set());
const managed = ref([]);
const supplement = ref({});
const lastRun = ref({});
const snackbar = ref({ show: false, text: '', color: 'success' });
const diagnostics = ref({ show: false, title: '', attempts: [] });

const groups = [
  { title: '全部', value: 'all' },
  { title: '失败', value: 'failure' },
  { title: '成功', value: 'success' },
  { title: '跳过', value: 'skipped' },
];

const categories = [
  { title: '全部地区', value: '' },
  { title: '国产剧', value: 'domestic' },
  { title: '欧美剧', value: 'western' },
  { title: '日韩剧', value: 'japan_korea' },
  { title: '其他地区', value: 'other' },
];

const historyHeaders = [
  { title: '标题', key: 'title', minWidth: 180 },
  { title: '状态', key: 'status', width: 150 },
  { title: '地区', key: 'category', width: 100 },
  { title: '豆瓣总集数', key: 'douban_total', width: 112 },
  { title: 'TMDB / 季', key: 'tmdb', width: 130 },
  { title: '时间', key: 'time', minWidth: 190 },
  { title: '原因', key: 'reason', minWidth: 260 },
  { title: '', key: 'actions', sortable: false, width: 96, align: 'end' },
];

const managedHeaders = [
  { title: '订阅', key: 'title', minWidth: 200 },
  { title: '季度', key: 'season', width: 80 },
  { title: '目标总集数', key: 'expected_total', width: 112 },
  { title: '状态', key: 'status', width: 180 },
  { title: '下次检查', key: 'check_after', minWidth: 190 },
  { title: '说明', key: 'reason', minWidth: 260 },
];

const supplementHeaders = [
  { title: '订阅', key: 'title', minWidth: 200 },
  { title: '早间进度', key: 'start_progress', width: 110 },
  { title: '当前进度', key: 'current_progress', width: 110 },
  { title: '状态', key: 'status', width: 150 },
  { title: '搜索时间', key: 'searched_at', minWidth: 190 },
];

const supplementItems = computed(() => supplement.value?.items || []);

function unwrap(response) {
  if (
    response
    && Object.prototype.hasOwnProperty.call(response, 'data')
    && response.success !== undefined
  ) {
    return response.data
  }
  return response?.data ?? response
}

function notify(text, color = 'success') {
  snackbar.value = { show: true, text, color };
}

function statusColor(status) {
  if (['subscribed', 'existing', 'history_existing'].includes(status)) return 'success'
  if (status === 'category_skipped') return 'warning'
  return 'error'
}

function categoryLabel(value) {
  return categories.find(item => item.value === value)?.title || value || '-'
}

function displayRow(record) {
  return {
    ...record,
    tmdb: record.tmdb_id
      ? `${record.tmdb_id} / S${String(record.season || 1).padStart(2, '0')}`
      : '',
  }
}

async function loadOverview() {
  try {
    const response = unwrap(await props.api.get('plugin/DoubanSubscribe/history'));
    managed.value = response?.managed || [];
    supplement.value = response?.supplement || {};
    lastRun.value = response?.last_run || {};
  } catch (error) {
    notify(error?.message || '状态加载失败', 'error');
  }
}

async function loadHistory() {
  loading.value = true;
  try {
    const params = {
      keyword: keyword.value,
      group: group.value === 'all' ? '' : group.value,
      category: category.value,
      offset: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
    };
    const response = unwrap(
      await props.api.get('plugin/DoubanSubscribe/history/search', { params }),
    );
    rows.value = (response?.items || []).map(displayRow);
    total.value = Number(response?.total || 0);
  } catch (error) {
    notify(error?.message || 'RSS 处理记录加载失败', 'error');
  } finally {
    loading.value = false;
  }
}

function search() {
  keyword.value = keywordInput.value.trim();
  page.value = 1;
  loadHistory();
}

function clearSearch() {
  keywordInput.value = '';
  keyword.value = '';
  page.value = 1;
  loadHistory();
}

async function runNow() {
  running.value = true;
  try {
    const response = unwrap(await props.api.post('plugin/DoubanSubscribe/run'));
    notify(response?.message || 'RSS 处理已启动', response?.success === false ? 'error' : 'success');
  } catch (error) {
    notify(error?.message || '启动失败', 'error');
  } finally {
    running.value = false;
  }
}

async function retry(record) {
  const next = new Set(retrying.value);
  next.add(record.key);
  retrying.value = next;
  try {
    const response = unwrap(
      await props.api.post('plugin/DoubanSubscribe/history/retry', { key: record.key }),
    );
    notify(response?.message || '重试完成', response?.success === false ? 'error' : 'success');
    await Promise.all([loadHistory(), loadOverview()]);
  } catch (error) {
    notify(error?.message || '重试失败', 'error');
  } finally {
    const done = new Set(retrying.value);
    done.delete(record.key);
    retrying.value = done;
  }
}

function showDiagnostics(record) {
  diagnostics.value = {
    show: true,
    title: record.title || 'TMDB 查询诊断',
    attempts: record.search_attempts || [],
  };
}

watch([group, category], () => {
  if (page.value !== 1) {
    page.value = 1;
  } else {
    loadHistory();
  }
});

watch([page, pageSize], () => {
  loadHistory();
});

onMounted(() => {
  loadHistory();
  loadOverview();
});

return (_ctx, _cache) => {
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VTooltip = _resolveComponent("VTooltip");
  const _component_VToolbar = _resolveComponent("VToolbar");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VTab = _resolveComponent("VTab");
  const _component_VTabs = _resolveComponent("VTabs");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VBtnToggle = _resolveComponent("VBtnToggle");
  const _component_VSelect = _resolveComponent("VSelect");
  const _component_VChip = _resolveComponent("VChip");
  const _component_VDataTableServer = _resolveComponent("VDataTableServer");
  const _component_VWindowItem = _resolveComponent("VWindowItem");
  const _component_VDataTable = _resolveComponent("VDataTable");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VWindow = _resolveComponent("VWindow");
  const _component_VTable = _resolveComponent("VTable");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VDialog = _resolveComponent("VDialog");
  const _component_VSnackbar = _resolveComponent("VSnackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      density: "comfortable",
      class: "page-toolbar"
    }, {
      default: _withCtx(() => [
        _cache[12] || (_cache[12] = _createElementVNode("div", { class: "text-h6 ms-3" }, "豆瓣订阅助手", -1)),
        _createVNode(_component_VSpacer),
        _createVNode(_component_VTooltip, { text: "立即处理 RSS" }, {
          activator: _withCtx(({ props: tooltipProps }) => [
            _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
              icon: "mdi-play",
              variant: "text",
              loading: running.value,
              onClick: runNow
            }), null, 16, ["loading"])
          ]),
          _: 1
        }),
        _createVNode(_component_VTooltip, { text: "刷新" }, {
          activator: _withCtx(({ props: tooltipProps }) => [
            _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
              icon: "mdi-refresh",
              variant: "text",
              loading: loading.value,
              onClick: _cache[0] || (_cache[0] = $event => (_ctx.Promise.all([loadHistory(), loadOverview()])))
            }), null, 16, ["loading"])
          ]),
          _: 1
        }),
        _createVNode(_component_VTooltip, { text: "关闭" }, {
          activator: _withCtx(({ props: tooltipProps }) => [
            _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
              icon: "mdi-close",
              variant: "text",
              onClick: _cache[1] || (_cache[1] = $event => (emit('close')))
            }), null, 16)
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VDivider),
    _createVNode(_component_VTabs, {
      modelValue: activeTab.value,
      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((activeTab).value = $event)),
      density: "comfortable"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VTab, { value: "history" }, {
          default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
            _createTextVNode("RSS 处理记录", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_VTab, { value: "managed" }, {
          default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
            _createTextVNode("受管订阅", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_VTab, { value: "supplement" }, {
          default: _withCtx(() => [...(_cache[15] || (_cache[15] = [
            _createTextVNode("今日补齐", -1)
          ]))]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VDivider),
    _createVNode(_component_VWindow, {
      modelValue: activeTab.value,
      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((activeTab).value = $event))
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VWindowItem, { value: "history" }, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_2, [
              _createElementVNode("div", _hoisted_3, [
                _createVNode(_component_VTextField, {
                  modelValue: keywordInput.value,
                  "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((keywordInput).value = $event)),
                  label: "搜索处理记录",
                  "prepend-inner-icon": "mdi-magnify",
                  density: "compact",
                  "hide-details": "",
                  clearable: "",
                  onKeyup: _withKeys(search, ["enter"]),
                  "onClick:clear": clearSearch
                }, null, 8, ["modelValue"]),
                _createVNode(_component_VTooltip, { text: "搜索" }, {
                  activator: _withCtx(({ props: tooltipProps }) => [
                    _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
                      icon: "mdi-magnify",
                      color: "primary",
                      variant: "tonal",
                      onClick: search
                    }), null, 16)
                  ]),
                  _: 1
                }),
                _createVNode(_component_VTooltip, { text: "清除" }, {
                  activator: _withCtx(({ props: tooltipProps }) => [
                    _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
                      icon: "mdi-filter-remove-outline",
                      variant: "text",
                      onClick: clearSearch
                    }), null, 16)
                  ]),
                  _: 1
                })
              ]),
              _createElementVNode("div", _hoisted_4, [
                _createVNode(_component_VBtnToggle, {
                  modelValue: group.value,
                  "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((group).value = $event)),
                  mandatory: "",
                  density: "compact",
                  color: "primary",
                  divided: ""
                }, {
                  default: _withCtx(() => [
                    (_openBlock(), _createElementBlock(_Fragment, null, _renderList(groups, (item) => {
                      return _createVNode(_component_VBtn, {
                        key: item.value,
                        value: item.value
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode(_toDisplayString(item.title), 1)
                        ]),
                        _: 2
                      }, 1032, ["value"])
                    }), 64))
                  ]),
                  _: 1
                }, 8, ["modelValue"]),
                _createVNode(_component_VSelect, {
                  modelValue: category.value,
                  "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((category).value = $event)),
                  items: categories,
                  label: "地区",
                  density: "compact",
                  "hide-details": "",
                  class: "category-select"
                }, null, 8, ["modelValue"]),
                _createElementVNode("div", _hoisted_5, " 共 " + _toDisplayString(total.value) + " 条 ", 1)
              ])
            ]),
            _createVNode(_component_VDataTableServer, {
              page: page.value,
              "onUpdate:page": _cache[6] || (_cache[6] = $event => ((page).value = $event)),
              "items-per-page": pageSize.value,
              "onUpdate:itemsPerPage": _cache[7] || (_cache[7] = $event => ((pageSize).value = $event)),
              headers: historyHeaders,
              items: rows.value,
              "items-length": total.value,
              loading: loading.value,
              "items-per-page-options": [10, 25, 50, 100],
              "item-value": "key",
              "fixed-header": "",
              class: "history-table"
            }, {
              "item.title": _withCtx(({ item }) => [
                _createElementVNode("div", _hoisted_6, [
                  _createElementVNode("div", null, _toDisplayString(item.douban_title || item.title), 1),
                  (item.douban_id)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_7, " 豆瓣 " + _toDisplayString(item.douban_id), 1))
                    : _createCommentVNode("", true)
                ])
              ]),
              "item.status": _withCtx(({ item }) => [
                _createVNode(_component_VChip, {
                  color: statusColor(item.status),
                  size: "small",
                  variant: "tonal"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(item.status), 1)
                  ]),
                  _: 2
                }, 1032, ["color"])
              ]),
              "item.category": _withCtx(({ item }) => [
                _createTextVNode(_toDisplayString(categoryLabel(item.category)), 1)
              ]),
              "item.actions": _withCtx(({ item }) => [
                _createElementVNode("div", _hoisted_8, [
                  (item.search_attempts?.length)
                    ? (_openBlock(), _createBlock(_component_VTooltip, {
                        key: 0,
                        text: "TMDB 查询诊断"
                      }, {
                        activator: _withCtx(({ props: tooltipProps }) => [
                          _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
                            icon: "mdi-text-search",
                            size: "small",
                            variant: "text",
                            onClick: $event => (showDiagnostics(item))
                          }), null, 16, ["onClick"])
                        ]),
                        _: 2
                      }, 1024))
                    : _createCommentVNode("", true),
                  (item.retryable)
                    ? (_openBlock(), _createBlock(_component_VTooltip, {
                        key: 1,
                        text: "重试"
                      }, {
                        activator: _withCtx(({ props: tooltipProps }) => [
                          _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
                            icon: "mdi-refresh",
                            size: "small",
                            variant: "text",
                            color: "primary",
                            loading: retrying.value.has(item.key),
                            onClick: $event => (retry(item))
                          }), null, 16, ["loading", "onClick"])
                        ]),
                        _: 2
                      }, 1024))
                    : _createCommentVNode("", true)
                ])
              ]),
              _: 1
            }, 8, ["page", "items-per-page", "items", "items-length", "loading"])
          ]),
          _: 1
        }),
        _createVNode(_component_VWindowItem, { value: "managed" }, {
          default: _withCtx(() => [
            _createVNode(_component_VDataTable, {
              headers: managedHeaders,
              items: managed.value,
              "items-per-page": 25,
              "fixed-header": ""
            }, null, 8, ["items"])
          ]),
          _: 1
        }),
        _createVNode(_component_VWindowItem, { value: "supplement" }, {
          default: _withCtx(() => [
            (supplement.value.date)
              ? (_openBlock(), _createBlock(_component_VAlert, {
                  key: 0,
                  type: "info",
                  variant: "tonal",
                  density: "compact",
                  class: "supplement-status"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(supplement.value.date) + " · " + _toDisplayString(supplement.value.status || '已建立快照'), 1)
                  ]),
                  _: 1
                }))
              : _createCommentVNode("", true),
            _createVNode(_component_VDataTable, {
              headers: supplementHeaders,
              items: supplementItems.value,
              "items-per-page": 25,
              "fixed-header": ""
            }, null, 8, ["items"])
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_VDialog, {
      modelValue: diagnostics.value.show,
      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((diagnostics.value.show) = $event)),
      "max-width": "860"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, null, {
          default: _withCtx(() => [
            _createVNode(_component_VToolbar, {
              density: "compact",
              color: "transparent"
            }, {
              default: _withCtx(() => [
                _createElementVNode("div", _hoisted_9, _toDisplayString(diagnostics.value.title), 1),
                _createVNode(_component_VSpacer),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  variant: "text",
                  onClick: _cache[9] || (_cache[9] = $event => (diagnostics.value.show = false))
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VDivider),
            _createVNode(_component_VTable, {
              density: "compact",
              class: "diagnostics-table"
            }, {
              default: _withCtx(() => [
                _cache[16] || (_cache[16] = _createElementVNode("thead", null, [
                  _createElementVNode("tr", null, [
                    _createElementVNode("th", null, "查询词"),
                    _createElementVNode("th", null, "模式"),
                    _createElementVNode("th", null, "结果"),
                    _createElementVNode("th", null, "详情"),
                    _createElementVNode("th", null, "请求"),
                    _createElementVNode("th", null, "错误")
                  ])
                ], -1)),
                _createElementVNode("tbody", null, [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(diagnostics.value.attempts, (attempt, index) => {
                    return (_openBlock(), _createElementBlock("tr", { key: index }, [
                      _createElementVNode("td", null, _toDisplayString(attempt.query), 1),
                      _createElementVNode("td", null, _toDisplayString(attempt.mode), 1),
                      _createElementVNode("td", null, _toDisplayString(attempt.result_count), 1),
                      _createElementVNode("td", null, _toDisplayString(attempt.hydrated_count), 1),
                      _createElementVNode("td", null, _toDisplayString(attempt.request_count), 1),
                      _createElementVNode("td", _hoisted_10, _toDisplayString(attempt.error || '-'), 1)
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
    }, 8, ["modelValue"]),
    _createVNode(_component_VSnackbar, {
      modelValue: snackbar.value.show,
      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((snackbar.value.show) = $event)),
      color: snackbar.value.color,
      timeout: "3500"
    }, {
      default: _withCtx(() => [
        _createTextVNode(_toDisplayString(snackbar.value.text), 1)
      ]),
      _: 1
    }, 8, ["modelValue", "color"])
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-af30cd34"]]);

export { Page as default };
