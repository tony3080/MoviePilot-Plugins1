import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { _ as _export_sfc } from './_plugin-vue_export-helper-pcqpp-6-.js';

const {resolveComponent:_resolveComponent,createVNode:_createVNode,createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,mergeProps:_mergeProps,withCtx:_withCtx,createTextVNode:_createTextVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "page-root" };
const _hoisted_2 = { class: "text-caption text-medium-emphasis" };
const _hoisted_3 = { class: "summary-grid" };
const _hoisted_4 = { class: "text-h5" };
const _hoisted_5 = { class: "text-h5" };
const _hoisted_6 = { class: "text-h5" };
const _hoisted_7 = { class: "text-h5" };
const _hoisted_8 = { class: "status-row" };

const {onMounted,ref} = await importShared('vue');



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
const overview = ref({ plugin: {}, counts: {}, capabilities: {} });
const errorMessage = ref('');

function unwrap(response) {
  return response?.data ?? response
}

async function loadOverview() {
  loading.value = true;
  errorMessage.value = '';
  try {
    overview.value = unwrap(
      await props.api.get('plugin/RssAllInOne/overview'),
    ) || overview.value;
  } catch (error) {
    errorMessage.value = error?.message || '状态加载失败';
  } finally {
    loading.value = false;
  }
}

onMounted(loadOverview);

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VTooltip = _resolveComponent("VTooltip");
  const _component_VToolbar = _resolveComponent("VToolbar");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VSheet = _resolveComponent("VSheet");
  const _component_VChip = _resolveComponent("VChip");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      density: "comfortable",
      color: "transparent"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VIcon, {
          icon: "mdi-rss",
          color: "primary",
          class: "ms-3 me-3"
        }),
        _createElementVNode("div", null, [
          _cache[1] || (_cache[1] = _createElementVNode("div", { class: "text-h6" }, "RSS一条龙", -1)),
          _createElementVNode("div", _hoisted_2, "v" + _toDisplayString(overview.value.plugin?.version || '0.4.0'), 1)
        ]),
        _createVNode(_component_VSpacer),
        _createVNode(_component_VTooltip, { text: "刷新状态" }, {
          activator: _withCtx(({ props: tooltipProps }) => [
            _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
              icon: "mdi-refresh",
              variant: "text",
              loading: loading.value,
              "aria-label": "刷新状态",
              onClick: loadOverview
            }), null, 16, ["loading"])
          ]),
          _: 1
        }),
        _createVNode(_component_VTooltip, { text: "插件设置" }, {
          activator: _withCtx(({ props: tooltipProps }) => [
            _createVNode(_component_VBtn, _mergeProps(tooltipProps, {
              icon: "mdi-cog-outline",
              variant: "text",
              "aria-label": "插件设置",
              onClick: _cache[0] || (_cache[0] = $event => (emit('switch')))
            }), null, 16)
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VDivider),
    (errorMessage.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 0,
          type: "error",
          variant: "tonal",
          class: "ma-4"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(errorMessage.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    _createElementVNode("div", _hoisted_3, [
      _createVNode(_component_VSheet, {
        border: "",
        class: "summary-item"
      }, {
        default: _withCtx(() => [
          _cache[2] || (_cache[2] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "媒体记录", -1)),
          _createElementVNode("div", _hoisted_4, _toDisplayString(overview.value.counts?.media || 0), 1)
        ]),
        _: 1
      }),
      _createVNode(_component_VSheet, {
        border: "",
        class: "summary-item"
      }, {
        default: _withCtx(() => [
          _cache[3] || (_cache[3] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "qB 快照", -1)),
          _createElementVNode("div", _hoisted_5, _toDisplayString(overview.value.counts?.torrents || 0), 1)
        ]),
        _: 1
      }),
      _createVNode(_component_VSheet, {
        border: "",
        class: "summary-item"
      }, {
        default: _withCtx(() => [
          _cache[4] || (_cache[4] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "RSS 任务", -1)),
          _createElementVNode("div", _hoisted_6, _toDisplayString(overview.value.counts?.rss_tasks || 0), 1)
        ]),
        _: 1
      }),
      _createVNode(_component_VSheet, {
        border: "",
        class: "summary-item"
      }, {
        default: _withCtx(() => [
          _cache[5] || (_cache[5] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "CD2 监控", -1)),
          _createElementVNode("div", _hoisted_7, _toDisplayString(overview.value.counts?.import_watches || 0), 1)
        ]),
        _: 1
      })
    ]),
    _createElementVNode("div", _hoisted_8, [
      _createVNode(_component_VChip, {
        color: overview.value.plugin?.enabled ? 'success' : 'default',
        variant: "tonal",
        size: "small"
      }, {
        default: _withCtx(() => [
          _createTextVNode(_toDisplayString(overview.value.plugin?.enabled ? '已启用' : '未启用'), 1)
        ]),
        _: 1
      }, 8, ["color"]),
      _createVNode(_component_VChip, {
        color: overview.value.capabilities?.clouddrive?.ready ? 'success' : 'warning',
        variant: "tonal",
        size: "small"
      }, {
        default: _withCtx(() => [
          _createTextVNode(" CloudDrive2 " + _toDisplayString(overview.value.capabilities?.clouddrive?.ready ? '依赖就绪' : '待配置'), 1)
        ]),
        _: 1
      }, 8, ["color"]),
      _createVNode(_component_VChip, {
        color: overview.value.capabilities?.local_inventory?.ready ? 'success' : 'warning',
        variant: "tonal",
        size: "small"
      }, {
        default: _withCtx(() => [
          _createTextVNode(" 本地库存 " + _toDisplayString(overview.value.capabilities?.local_inventory?.ready ? '可访问' : '待配置'), 1)
        ]),
        _: 1
      }, 8, ["color"]),
      _createVNode(_component_VChip, {
        color: "info",
        variant: "tonal",
        size: "small"
      }, {
        default: _withCtx(() => [...(_cache[6] || (_cache[6] = [
          _createTextVNode("QB 只读阶段", -1)
        ]))]),
        _: 1
      })
    ])
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-55ca8926"]]);

export { Page as default };
