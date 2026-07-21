<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { hasPermission } from "../api";
import { enterpriseApi } from "../services/enterprise";
import StatusPill from "../components/StatusPill.vue";
const route = useRoute(),
  router = useRouter(),
  data = ref<any>(null),
  options = ref<any>({ rooms: [], accounts: [], anchors: [] }),
  loading = ref(true),
  error = ref(""),
  notice = ref(""),
  tab = ref("status"),
  showBinding = ref(false),
  saving = ref(false);
const form = reactive({
  room_id: "",
  account_id: "",
  anchor_id: "",
  reason: "",
});
const deviceId = computed(() => String(route.params.deviceId)),
  device = computed(() => data.value?.device || {}),
  binding = computed(() => data.value?.binding);
const canWrite = computed(() => hasPermission("binding.write"));
const problems = computed(() => {
  const d = device.value,
    r: any[] = [];
  if (d.online_state !== "online")
    r.push({
      code: "DEVICE_OFFLINE",
      title: "设备心跳异常",
      impact: "企业后台无法确认当前环境和开播状态",
      advice: "检查客户端是否运行、电脑是否休眠以及本地网络连接",
    });
  if (d.studio_state !== "running")
    r.push({
      code: "LIVE_SOFTWARE_NOT_RUNNING",
      title: "LIVE Studio 未运行",
      impact: "当前电脑尚未启动直播软件",
      advice: "在电脑端确认安装路径并启动 TikTok LIVE Studio",
    });
  if (!["healthy", "ok"].includes(d.collector_state))
    r.push({
      code: "COLLECTOR_UNHEALTHY",
      title: "采集服务异常",
      impact: "实时指标可能不完整或已经过期",
      advice: "在客户端“帮助与诊断”中重新同步并检查诊断信息",
    });
  if (Number(d.metrics?.network_latency_ms || 0) > 150)
    r.push({
      code: "NETWORK_LATENCY_HIGH",
      title: "网络延迟偏高",
      impact: "推流稳定性可能下降",
      advice: "检查本地线路、Wi-Fi 干扰和目标地区链路",
    });
  if (Number(d.metrics?.upload_mbps || 999) < 8)
    r.push({
      code: "UPLOAD_BANDWIDTH_LOW",
      title: "上传带宽偏低",
      impact: "高码率推流可能卡顿",
      advice: "降低并发占用并联系网络服务商排查上行质量",
    });
  return r;
});
const conclusion = computed(() =>
  problems.value.some(
    (x) => x.code === "DEVICE_OFFLINE" || x.code === "COLLECTOR_UNHEALTHY",
  )
    ? "需要立即处理"
    : problems.value.length
      ? "存在开播风险"
      : "当前状态正常",
);
function points(key: string) {
  const values = (data.value?.metrics_60m || [])
    .map((x: any) => Number(x[key]))
    .filter(Number.isFinite);
  if (!values.length) return "";
  const max = Math.max(...values, 1),
    min = Math.min(...values, 0),
    span = Math.max(1, max - min);
  return values
    .map(
      (value: number, index: number) =>
        `${values.length === 1 ? 50 : (index / (values.length - 1)) * 100},${36 - ((value - min) / span) * 32}`,
    )
    .join(" ");
}
async function load() {
  loading.value = true;
  error.value = "";
  try {
    [data.value, options.value] = await Promise.all([
      enterpriseApi.device(deviceId.value),
      enterpriseApi.options(),
    ]);
    if (binding.value)
      Object.assign(form, {
        room_id: String(binding.value.room_id),
        account_id: String(binding.value.account_id || ""),
        anchor_id: String(binding.value.anchor_id || ""),
        reason: "设备资料调整",
      });
  } catch (e: any) {
    error.value = `${e.message}${e.requestId ? `（请求编号 ${e.requestId}）` : ""}`;
  } finally {
    loading.value = false;
  }
}
async function saveBinding() {
  if (!form.room_id || !form.reason.trim()) {
    error.value = "请选择直播间并填写换绑原因";
    return;
  }
  if (
    !window.confirm(
      binding.value
        ? "换绑会结束当前主绑定并保留完整历史，确认继续吗？"
        : "确认将这台设备绑定到所选直播间吗？",
    )
  )
    return;
  saving.value = true;
  try {
    await enterpriseApi.bindDevice(deviceId.value, {
      room_id: Number(form.room_id),
      account_id: form.account_id ? Number(form.account_id) : null,
      anchor_id: form.anchor_id ? Number(form.anchor_id) : null,
      binding_type: "primary",
      reason: form.reason,
    });
    showBinding.value = false;
    await load();
    notice.value =
      "设备绑定已更新，历史记录已保留；客户端下次同步会获得最新绑定。";
  } catch (e: any) {
    error.value = `绑定失败：${e.message}。当前绑定未被覆盖，请处理冲突后重试。`;
  } finally {
    saving.value = false;
  }
}
async function unbind() {
  const reason = window.prompt(
    "请输入解绑原因（会写入审计记录）",
    "设备停用或更换用途",
  );
  if (
    !reason ||
    !window.confirm(
      "解绑后该设备将不再关联直播间，历史记录会保留。确认继续吗？",
    )
  )
    return;
  try {
    await enterpriseApi.unbindDevice(deviceId.value, reason);
    await load();
    notice.value = "设备已解绑，原绑定已作为历史记录保留。";
  } catch (e: any) {
    error.value = e.message;
  }
}
onMounted(load);
</script>
<template>
  <div class="page-stack">
    <button
      class="back-link"
      @click="router.push({ name: 'enterprise-devices' })"
    >
      ← 返回设备中心
    </button>
    <div v-if="error && !data" class="panel state-panel error">
      <span class="state-icon">!</span>
      <h3>设备详情暂时不可用</h3>
      <p>{{ error }}</p>
      <button class="primary" @click="load">重新加载</button>
    </div>
    <div
      v-else-if="loading && !data"
      class="panel skeleton detail-skeleton"
    ></div>
    <template v-else-if="data"
      ><section
        :class="['device-conclusion', problems.length ? 'warning' : 'healthy']"
      >
        <div>
          <span class="eyebrow light">DEVICE READINESS</span>
          <h2>{{ conclusion }}</h2>
          <p>
            {{
              problems[0]?.impact ||
              "设备在线、采集服务和直播软件状态均未发现异常。"
            }}
          </p>
        </div>
        <div class="device-conclusion-status">
          <StatusPill :value="device.online_state" /><StatusPill
            :value="device.studio_state"
          /><StatusPill :value="device.collector_state" />
        </div>
      </section>
      <div v-if="notice" class="success-banner">{{ notice }}</div>
      <div v-if="error" class="form-error">{{ error }}</div>
      <section class="panel">
        <header class="panel-head">
          <div>
            <span class="eyebrow">{{ device.device_id }}</span>
            <h2>{{ device.display_name }}</h2>
            <p>
              {{ device.store_name || "未设置门店" }} ·
              {{ device.location || "未设置位置" }} ·
              {{ device.owner_name || "未设置负责人" }}
            </p>
          </div>
          <div class="action-cluster">
            <button @click="load">重新同步状态</button
            ><button @click="tab = 'diagnosis'">查看诊断</button
            ><button v-if="canWrite && binding" class="danger-button" @click="unbind">
              解绑</button
            ><button v-if="canWrite" class="primary" @click="showBinding = true">
              {{ binding ? "换绑" : "首次绑定" }}
            </button>
          </div>
        </header>
        <div class="detail-tabs">
          <button
            v-for="x in [
              { id: 'status', name: '当前状态' },
              { id: 'binding', name: '绑定历史' },
              { id: 'metrics', name: '60分钟指标' },
              { id: 'diagnosis', name: '异常与建议' },
              { id: 'audit', name: '操作审计' },
            ]"
            :class="{ active: tab === x.id }"
            @click="tab = x.id"
          >
            {{ x.name }}
          </button>
        </div>
        <div v-if="tab === 'status'" class="detail-section">
          <div class="detail-facts">
            <article>
              <span>客户端版本</span><b>V{{ device.agent_version || "-" }}</b
              ><small>最低版本由企业配置统一下发</small>
            </article>
            <article>
              <span>当前直播间</span
              ><b>{{
                data.binding_history.find((x: any) => x.id === binding?.id)
                  ?.room_name || "未绑定"
              }}</b
              ><small>{{
                binding ? `绑定版本 ${binding.version}` : "需要完成绑定"
              }}</small>
            </article>
            <article>
              <span>最后心跳</span
              ><b>{{
                device.last_heartbeat_at?.replace("T", " ").slice(0, 19) ||
                "尚未上报"
              }}</b
              ><small>{{ device.online_state }}</small>
            </article>
            <article>
              <span>CPU / 内存</span
              ><b
                >{{ device.metrics.cpu_percent ?? "-" }}% /
                {{ device.metrics.memory_percent ?? "-" }}%</b
              ><small>最近一次轻量采样</small>
            </article>
            <article>
              <span>网络延迟</span
              ><b>{{ device.metrics.network_latency_ms ?? "-" }} ms</b
              ><small>上传 {{ device.metrics.upload_mbps ?? "-" }} Mbps</small>
            </article>
            <article>
              <span>推流状态</span
              ><b>{{ device.metrics.stream_bitrate_kbps ?? "-" }} Kbps</b
              ><small>丢帧 {{ device.metrics.dropped_frames ?? "-" }}</small>
            </article>
          </div>
        </div>
        <div v-else-if="tab === 'binding'" class="detail-section">
          <div v-if="!data.binding_history.length" class="empty-state">
            这台设备还没有绑定历史。
          </div>
          <div v-else class="timeline">
            <article v-for="x in data.binding_history" :key="x.id">
              <i></i>
              <div>
                <b
                  >{{ x.status === "active" ? "当前绑定" : "历史绑定" }} ·
                  {{ x.room_name || `直播间 #${x.room_id}` }}</b
                >
                <p>
                  账号 {{ x.account_name || "未关联" }} · 主播
                  {{ x.anchor_name || "未关联" }} ·
                  {{ x.reason || "未填写原因" }}
                </p>
              </div>
              <small>{{
                String(x.bound_at).replace("T", " ").slice(0, 19)
              }}</small>
            </article>
          </div>
        </div>
        <div v-else-if="tab === 'metrics'" class="detail-section">
          <div v-if="!data.metrics_60m.length" class="empty-state">
            <b>最近 60 分钟没有指标</b>
            <p>设备恢复心跳后，CPU、内存、网络与上传趋势会显示在这里。</p>
          </div>
          <div v-else class="trend-grid">
            <article
              v-for="metric in [
                { key: 'cpu_percent', name: 'CPU', unit: '%' },
                { key: 'memory_percent', name: '内存', unit: '%' },
                { key: 'network_latency_ms', name: '延迟', unit: 'ms' },
                { key: 'upload_mbps', name: '上传', unit: 'Mbps' },
              ]"
              :key="metric.key"
            >
              <header>
                <b>{{ metric.name }}</b
                ><span
                  >{{ data.metrics_60m.at(-1)?.[metric.key] ?? "-" }}
                  {{ metric.unit }}</span
                >
              </header>
              <svg viewBox="0 0 100 40" preserveAspectRatio="none">
                <polyline :points="points(metric.key)" />
              </svg>
            </article>
          </div>
        </div>
        <div v-else-if="tab === 'diagnosis'" class="detail-section">
          <div v-if="!problems.length" class="empty-state success-empty">
            <b>当前没有需要处理的异常</b>
            <p>建议开播前仍在客户端执行一次完整环境检测。</p>
          </div>
          <div v-else class="diagnosis-list">
            <article v-for="x in problems">
              <header>
                <b>{{ x.title }}</b
                ><code>{{ x.code }}</code>
              </header>
              <dl>
                <div>
                  <dt>系统检查</dt>
                  <dd>依据设备最新心跳和轻量指标判断</dd>
                </div>
                <div>
                  <dt>影响</dt>
                  <dd>{{ x.impact }}</dd>
                </div>
                <div>
                  <dt>建议</dt>
                  <dd>{{ x.advice }}</dd>
                </div>
                <div>
                  <dt>恢复状态</dt>
                  <dd>等待下一次有效心跳自动复核</dd>
                </div>
              </dl>
            </article>
          </div>
        </div>
        <div v-else class="detail-section">
          <div v-if="!data.audit.length" class="empty-state">
            暂无与这台设备相关的审计记录。
          </div>
          <div v-else class="timeline">
            <article v-for="x in data.audit">
              <i></i>
              <div>
                <b>{{ x.action }}</b>
                <p>{{ x.actor }} · {{ x.target_type }} / {{ x.target_id }}</p>
              </div>
              <small>{{ x.created_at?.replace("T", " ").slice(0, 19) }}</small>
            </article>
          </div>
        </div>
      </section></template
    >
    <div
      v-if="showBinding"
      class="modal-mask"
      @click.self="showBinding = false"
    >
      <form class="binding-modal" @submit.prevent="saveBinding">
        <header>
          <div>
            <span class="eyebrow">DEVICE BINDING</span>
            <h2>{{ binding ? "更换设备主绑定" : "建立设备主绑定" }}</h2>
            <p>换绑不会覆盖历史；冲突时服务端返回 409 并保留当前状态。</p>
          </div>
          <button
            type="button"
            class="drawer-close"
            @click="showBinding = false"
          >
            ×
          </button>
        </header>
        <label
          >直播间<select v-model="form.room_id" required>
            <option value="" disabled>选择直播间</option>
            <option v-for="x in options.rooms" :value="String(x.id)">
              {{ x.name }}
            </option>
          </select></label
        ><label
          >开播账号<select v-model="form.account_id">
            <option value="">不关联账号</option>
            <option
              v-for="x in options.accounts.filter(
                (a: any) => !a.room_id || String(a.room_id) === form.room_id,
              )"
              :value="String(x.id)"
            >
              {{ x.display_name }}
            </option>
          </select></label
        ><label
          >主播<select v-model="form.anchor_id">
            <option value="">不关联主播</option>
            <option v-for="x in options.anchors" :value="String(x.id)">
              {{ x.display_name }}
            </option>
          </select></label
        ><label
          >操作原因<textarea
            v-model="form.reason"
            rows="3"
            required
            placeholder="填写换绑原因或工单编号"
          ></textarea>
        </label>
        <footer>
          <button type="button" @click="showBinding = false">取消</button
          ><button class="primary" :disabled="saving">
            {{ saving ? "提交中…" : "确认并保留历史" }}
          </button>
        </footer>
      </form>
    </div>
  </div>
</template>
