<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['save', 'close'])

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
  minimum_year: 0,
  notify_subscription: true,
  media_categories: ['domestic', 'western', 'japan_korea', 'other'],
}

const categories = [
  { title: '国产剧', value: 'domestic' },
  { title: '欧美剧', value: 'western' },
  { title: '日韩剧', value: 'japan_korea' },
  { title: '其他地区', value: 'other' },
]

const maoyanTypes = [
  { title: '电视剧热度榜', value: 'tv' },
  { title: '网剧热度榜', value: 'web' },
]

const config = ref({ ...defaults })

function save() {
  emit('save', JSON.parse(JSON.stringify(config.value)))
}

onMounted(() => {
  config.value = {
    ...defaults,
    ...JSON.parse(JSON.stringify(props.initialConfig || {})),
  }
  if (!Array.isArray(config.value.media_categories)) {
    config.value.media_categories = [...defaults.media_categories]
  }
  if (!Array.isArray(config.value.maoyan_types)) {
    config.value.maoyan_types = [...defaults.maoyan_types]
  }
})
</script>

<template>
  <div class="config-root">
    <VToolbar density="comfortable" color="transparent">
      <div class="text-h6 ms-3">豆瓣订阅助手配置</div>
      <VSpacer />
      <VTooltip text="保存">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-content-save"
            variant="text"
            color="primary"
            @click="save"
          />
        </template>
      </VTooltip>
      <VTooltip text="关闭">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon="mdi-close"
            variant="text"
            @click="emit('close')"
          />
        </template>
      </VTooltip>
    </VToolbar>
    <VDivider />

    <VForm class="config-form">
      <VRow>
        <VCol cols="12" md="3">
          <VSwitch v-model="config.enabled" label="启用插件" color="primary" />
        </VCol>
        <VCol cols="12" md="3">
          <VSwitch v-model="config.onlyonce" label="立即运行一次" color="primary" />
        </VCol>
        <VCol cols="12" md="3">
          <VSwitch v-model="config.proxy" label="内容源使用代理" color="primary" />
        </VCol>
        <VCol cols="12" md="3">
          <VSwitch
            v-model="config.notify_subscription"
            label="订阅成功通知"
            color="primary"
          />
        </VCol>
        <VCol cols="12">
          <VTextarea
            v-model="config.rss_urls"
            label="RSS 地址（每行一个）"
            rows="4"
            auto-grow
          />
        </VCol>
        <VCol cols="12" md="4">
          <VSwitch
            v-model="config.maoyan_enabled"
            label="启用猫眼全网榜单"
            color="primary"
          />
        </VCol>
        <VCol cols="12" md="5">
          <VSelect
            v-model="config.maoyan_types"
            :items="maoyanTypes"
            label="猫眼榜单"
            multiple
            chips
            closable-chips
            :disabled="!config.maoyan_enabled"
          />
        </VCol>
        <VCol cols="12" md="3">
          <VTextField
            v-model.number="config.maoyan_num"
            label="每榜处理条数"
            type="number"
            min="1"
            max="30"
            :disabled="!config.maoyan_enabled"
          />
        </VCol>
        <VCol cols="12" md="4">
          <VTextField v-model="config.cron" label="内容源执行周期" />
        </VCol>
        <VCol cols="12" md="4">
          <VTextField
            v-model="config.supplement_cron"
            label="订阅补齐执行周期"
            hint="每日 08:00 建立快照，到此周期检查订阅进度"
            persistent-hint
          />
        </VCol>
        <VCol cols="12" md="4">
          <VTextField
            v-model.number="config.max_items"
            label="每个 RSS 最大条目数"
            type="number"
            min="1"
            max="200"
          />
        </VCol>
        <VCol cols="12" md="4">
          <VTextField
            v-model.number="config.candidate_limit"
            label="TMDB 候选详情上限"
            type="number"
            min="1"
            max="30"
          />
        </VCol>
        <VCol cols="12" md="4">
          <VTextField
            v-model.number="config.confirmation_days"
            label="完成后二次确认天数"
            type="number"
            min="1"
            max="365"
          />
        </VCol>
        <VCol cols="12" md="4">
          <VTextField
            v-model.number="config.minimum_year"
            label="首播年份下限"
            type="number"
            min="0"
            max="2100"
            hint="0 表示不限制；设置 2026 时仅订阅 2026 年及以后首播的剧集"
            persistent-hint
          />
        </VCol>
        <VCol cols="12">
          <VSelect
            v-model="config.media_categories"
            :items="categories"
            label="需要订阅的剧集类型"
            multiple
            chips
            closable-chips
          />
        </VCol>
      </VRow>
    </VForm>
  </div>
</template>

<style scoped>
.config-root {
  min-width: 0;
}

.config-form {
  padding: 16px;
}
</style>
