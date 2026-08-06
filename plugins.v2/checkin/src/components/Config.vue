<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['save', 'close'])
const showSmzdmCookie = ref(false)
const showChiphellCookie = ref(false)

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
}

const config = ref({ ...defaults })

function save() {
  emit('save', JSON.parse(JSON.stringify(config.value)))
}

onMounted(() => {
  config.value = {
    ...defaults,
    ...JSON.parse(JSON.stringify(props.initialConfig || {})),
  }
})
</script>

<template>
  <div class="config-root">
    <VToolbar density="comfortable" color="transparent">
      <div class="text-h6 ms-3">签到助手配置</div>
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
          <VSwitch v-model="config.notify" label="发送结果通知" color="primary" />
        </VCol>
        <VCol cols="12" md="3">
          <VTextField
            v-model.number="config.history_days"
            label="历史保留天数"
            type="number"
            min="1"
            max="365"
          />
        </VCol>
      </VRow>

      <div class="section-title">什么值得买</div>
      <VRow>
        <VCol cols="12" md="4">
          <VSwitch v-model="config.smzdm_enabled" label="启用定时签到" color="primary" />
        </VCol>
        <VCol cols="12" md="4">
          <VTextField v-model="config.smzdm_cron" label="执行周期" />
        </VCol>
        <VCol cols="12">
          <VTextField
            v-model="config.smzdm_cookie"
            label="登录 Cookie"
            :type="showSmzdmCookie ? 'text' : 'password'"
            autocomplete="off"
            :append-inner-icon="showSmzdmCookie ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
            @click:append-inner="showSmzdmCookie = !showSmzdmCookie"
          />
        </VCol>
      </VRow>

      <VDivider class="section-divider" />
      <div class="section-title">Chiphell</div>
      <VRow>
        <VCol cols="12" md="4">
          <VSwitch v-model="config.chiphell_enabled" label="启用定时保活" color="primary" />
        </VCol>
        <VCol cols="12" md="4">
          <VTextField v-model="config.chiphell_cron" label="执行周期" />
        </VCol>
        <VCol cols="12">
          <VTextField
            v-model="config.chiphell_cookie"
            label="登录 Cookie"
            :type="showChiphellCookie ? 'text' : 'password'"
            autocomplete="off"
            :append-inner-icon="showChiphellCookie ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
            @click:append-inner="showChiphellCookie = !showChiphellCookie"
          />
        </VCol>
      </VRow>
    </VForm>
  </div>
</template>

<style scoped>
.config-root { min-width: 0; }
.config-form { padding: 16px; }
.section-title { font-size: 16px; font-weight: 600; margin: 4px 0 8px; }
.section-divider { margin: 4px 0 18px; }
</style>
