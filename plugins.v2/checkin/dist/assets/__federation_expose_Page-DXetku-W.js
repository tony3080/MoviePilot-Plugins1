import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,mergeProps:_mergeProps,withCtx:_withCtx,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "page-root" };
const _hoisted_2 = { class: "actions-band" };
const _hoisted_3 = { class: "site-action" };
const _hoisted_4 = { class: "site-status" };
const _hoisted_5 = { class: "site-action" };
const _hoisted_6 = { class: "site-status" };
const _hoisted_7 = { class: "history-toolbar" };

const {computed,onMounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Page',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
},
  emits: ['switch', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;
const loading = ref(false);
const running = ref('');
const rows = ref([]);
const snackbar = ref({ show: false, text: '', color: 'success' });

const headers = [
  { title: '站点', key: 'site_name', width: 140 },
  { title: '状态', key: 'status_label', width: 120 },
  { title: '说明', key: 'message', minWidth: 260 },
  { title: '账号', key: 'username', width: 130 },
  { title: '连续签到', key: 'days', width: 110 },
  { title: '积分', key: 'points', width: 130 },
  { title: '触发', key: 'trigger_label', width: 90 },
  { title: '时间', key: 'date', width: 180 },
];

const summary = computed(() => {
  const latest = {};
  for (const row of rows.value) {
    if (!latest[row.site]) latest[row.site] = row;
  }
  return latest
});

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

function displayRow(record) {
  const statusLabels = {
    success: '成功',
    already: '今日已完成',
    failed: '失败',
    busy: '执行中',
  };
  return {
    ...record,
    status_label: statusLabels[record.status] || record.status || '-',
    trigger_label: record.trigger === 'scheduled' ? '定时' : '手动',
  }
}

function statusColor(status) {
  if (status === 'success') return 'success'
  if (status === 'already') return 'info'
  if (status === 'busy') return 'warning'
  return 'error'
}

async function loadHistory() {
  loading.value = true;
  try {
    const response = unwrap(await props.api.get('plugin/Checkin/history'));
    rows.value = (response?.items || []).map(displayRow);
  } catch (error) {
    notify(error?.message || '签到历史加载失败', 'error');
  } finally {
    loading.value = false;
  }
}

async function run(site) {
  running.value = site;
  try {
    const response = unwrap(await props.api.post('plugin/Checkin/run', { site }));
    notify(
      response?.message || '签到执行完成',
      response?.success === false ? 'error' : 'success',
    );
    await loadHistory();
  } catch (error) {
    notify(error?.message || '签到执行失败', 'error');
  } finally {
    running.value = '';
  }
}

async function clearHistory() {
  try {
    const response = unwrap(await props.api.post('plugin/Checkin/history/clear'));
    notify(response?.message || '签到历史已清空');
    await loadHistory();
  } catch (error) {
    notify(error?.message || '清空失败', 'error');
  }
}

onMounted(loadHistory);

return (_ctx, _cache) => {
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VTooltip = _resolveComponent("VTooltip");
  const _component_VToolbar = _resolveComponent("VToolbar");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VChip = _resolveComponent("VChip");
  const _component_VDataTable = _resolveComponent("VDataTable");
  const _component_VSnackbar = _resolveComponent("VSnackbar");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      density: "comfortable",
      color: "transparent"
    }, {
      default: _withCtx(() => [
        _cache[5] || (_cache[5] = _createElementVNode("div", { class: "text-h6 ms-3" }, "签到助手", -1)),
        _createVNode(_component_VSpacer),
        _createVNode(_component_VTooltip, { text: "刷新" }, {
          activator: _withCtx(({ props: tooltipProps }) => [
            _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
              icon: "mdi-refresh",
              variant: "text",
              loading: loading.value,
              onClick: loadHistory
            }), null, 16, ["loading"])
          ]),
          _: 1
        }),
        _createVNode(_component_VTooltip, { text: "设置" }, {
          activator: _withCtx(({ props: tooltipProps }) => [
            _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
              icon: "mdi-cog-outline",
              variant: "text",
              onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
            }), null, 16)
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
    _createElementVNode("div", _hoisted_2, [
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("div", null, [
          _cache[6] || (_cache[6] = _createElementVNode("div", { class: "site-name" }, "什么值得买", -1)),
          _createElementVNode("div", _hoisted_4, _toDisplayString(summary.value.smzdm?.message || '尚无执行记录'), 1)
        ]),
        _createVNode(_component_VBtn, {
          "prepend-icon": "mdi-calendar-check-outline",
          color: "primary",
          variant: "tonal",
          loading: running.value === 'smzdm',
          disabled: Boolean(running.value),
          onClick: _cache[2] || (_cache[2] = $event => (run('smzdm')))
        }, {
          default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
            _createTextVNode(" 立即签到 ", -1)
          ]))]),
          _: 1
        }, 8, ["loading", "disabled"])
      ]),
      _createVNode(_component_VDivider, {
        vertical: "",
        class: "action-divider"
      }),
      _createElementVNode("div", _hoisted_5, [
        _createElementVNode("div", null, [
          _cache[8] || (_cache[8] = _createElementVNode("div", { class: "site-name" }, "Chiphell", -1)),
          _createElementVNode("div", _hoisted_6, _toDisplayString(summary.value.chiphell?.message || '尚无执行记录'), 1)
        ]),
        _createVNode(_component_VBtn, {
          "prepend-icon": "mdi-web-check",
          color: "secondary",
          variant: "tonal",
          loading: running.value === 'chiphell',
          disabled: Boolean(running.value),
          onClick: _cache[3] || (_cache[3] = $event => (run('chiphell')))
        }, {
          default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
            _createTextVNode(" 立即保活 ", -1)
          ]))]),
          _: 1
        }, 8, ["loading", "disabled"])
      ])
    ]),
    _createElementVNode("div", _hoisted_7, [
      _cache[10] || (_cache[10] = _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "执行历史", -1)),
      _createVNode(_component_VSpacer),
      _createVNode(_component_VTooltip, { text: "清空历史" }, {
        activator: _withCtx(({ props: tooltipProps }) => [
          _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
            icon: "mdi-delete-sweep-outline",
            variant: "text",
            size: "small",
            onClick: clearHistory
          }), null, 16)
        ]),
        _: 1
      })
    ]),
    _createVNode(_component_VDataTable, {
      headers: headers,
      items: rows.value,
      loading: loading.value,
      "items-per-page": 25,
      density: "comfortable",
      class: "history-table"
    }, {
      "item.status_label": _withCtx(({ item }) => [
        _createVNode(_component_VChip, {
          color: statusColor(item.status),
          size: "small",
          variant: "tonal"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(item.status_label), 1)
          ]),
          _: 2
        }, 1032, ["color"])
      ]),
      "item.days": _withCtx(({ item }) => [
        _createTextVNode(_toDisplayString(item.days ? `${item.days} 天` : '-'), 1)
      ]),
      "item.username": _withCtx(({ item }) => [
        _createTextVNode(_toDisplayString(item.username || '-'), 1)
      ]),
      "item.points": _withCtx(({ item }) => [
        _createTextVNode(_toDisplayString(item.points || '-'), 1)
      ]),
      "no-data": _withCtx(() => [...(_cache[11] || (_cache[11] = [
        _createElementVNode("div", { class: "empty-state" }, "暂无签到记录", -1)
      ]))]),
      _: 1
    }, 8, ["items", "loading"]),
    _createVNode(_component_VSnackbar, {
      modelValue: snackbar.value.show,
      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((snackbar.value.show) = $event)),
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
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-150ebeed"]]);

export { Page as default };
