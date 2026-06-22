<script setup lang="ts">
import { Lock, User } from "@element-plus/icons-vue";
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";

import { login, type ApiError } from "../api/client";
import { setToken } from "../composables/useAuth";
import BaseButton from "../components/ui/BaseButton.vue";

const router = useRouter();
const credentials = reactive({ username: "demo_user", password: "" });
const isSubmitting = ref(false);
const errorMessage = ref("");

async function submitLogin(): Promise<void> {
  if (!credentials.username || !credentials.password || isSubmitting.value) {
    return;
  }

  isSubmitting.value = true;
  errorMessage.value = "";
  try {
    const result = await login(credentials.username, credentials.password);
    setToken(result.access_token);
    await router.push("/");
  } catch (error) {
    errorMessage.value = (error as ApiError).message || "登录失败，请重试";
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <section class="login-page">
    <div class="login-page__signal" aria-hidden="true">
      <span>BR / 01</span>
      <i />
      <span>SECURE ACCESS</span>
    </div>

    <div class="login-page__panel">
      <header class="login-page__header">
        <span class="login-page__mark">账</span>
        <div>
          <p>银企对账 · 审计辅助工作台</p>
          <h1>进入对账现场</h1>
        </div>
      </header>

      <p class="login-page__lead">
        使用预置审计账号登录。系统将为后续接口与实时 Agent 流签发访问凭证。
      </p>

      <form class="login-page__form" @submit.prevent="submitLogin">
        <el-form label-position="top">
          <el-form-item label="用户名">
            <el-input
              v-model="credentials.username"
              autocomplete="username"
              placeholder="请输入用户名"
              size="large"
            >
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="credentials.password"
              autocomplete="current-password"
              placeholder="请输入密码"
              show-password
              size="large"
              type="password"
            >
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>
        </el-form>

        <p v-if="errorMessage" class="login-page__error" role="alert">{{ errorMessage }}</p>

        <BaseButton
          class="login-page__submit"
          :disabled="!credentials.username || !credentials.password"
          :loading="isSubmitting"
          @click="submitLogin"
        >
          验证并进入
        </BaseButton>
      </form>

      <footer>
        <span>JWT / HS256</span>
        <span>访问记录将纳入审计链路</span>
      </footer>
    </div>
  </section>
</template>

<style scoped>
.login-page {
  position: relative;
  display: grid;
  min-height: 100vh;
  place-items: center;
  overflow: hidden;
  padding: var(--space-8);
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--color-border-soft) 65%, transparent) 1px, transparent 1px),
    linear-gradient(color-mix(in srgb, var(--color-border-soft) 65%, transparent) 1px, transparent 1px),
    radial-gradient(circle at 18% 18%, var(--color-accent-soft), transparent 30%),
    var(--color-bg);
  background-size: 44px 44px, 44px 44px, auto, auto;
}

.login-page::after {
  position: absolute;
  right: -14vw;
  bottom: -32vw;
  width: 64vw;
  height: 64vw;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  content: "";
  box-shadow: 0 0 0 8vw color-mix(in srgb, var(--color-surface) 35%, transparent),
    0 0 0 16vw color-mix(in srgb, var(--color-surface) 20%, transparent);
}

.login-page__signal {
  position: absolute;
  top: var(--space-8);
  left: var(--space-8);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--color-text-subtle);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
}

.login-page__signal i {
  width: 48px;
  height: 1px;
  background: var(--color-accent);
}

.login-page__panel {
  position: relative;
  z-index: 1;
  width: min(100%, 500px);
  padding: var(--space-10);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--color-surface) 94%, transparent);
  box-shadow: var(--shadow-panel);
  backdrop-filter: blur(18px);
  animation: panel-in var(--duration-slow) var(--ease-standard) both;
}

.login-page__header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.login-page__mark {
  display: grid;
  width: 52px;
  height: 52px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: var(--radius-md);
  background: var(--color-text);
  color: var(--color-bg-soft);
  font-family: var(--font-serif);
  font-size: 24px;
}

.login-page__header p,
.login-page__header h1 {
  margin: 0;
}

.login-page__header p {
  color: var(--color-text-subtle);
  font-size: 12px;
  letter-spacing: 0.06em;
}

.login-page__header h1 {
  margin-top: var(--space-1);
  font-family: var(--font-serif);
  font-size: clamp(28px, 5vw, 38px);
  font-weight: 500;
  letter-spacing: -0.04em;
}

.login-page__lead {
  margin: var(--space-8) 0;
  color: var(--color-text-muted);
  font-size: 14px;
  line-height: 1.8;
}

.login-page__form :deep(.el-form-item) {
  margin-bottom: var(--space-5);
}

.login-page__error {
  margin: calc(var(--space-2) * -1) 0 var(--space-4);
  color: var(--color-danger);
  font-size: 13px;
}

.login-page__submit {
  width: 100%;
}

.login-page footer {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  margin-top: var(--space-8);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-border-soft);
  color: var(--color-text-subtle);
  font-family: var(--font-mono);
  font-size: 10px;
}

@keyframes panel-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 560px) {
  .login-page { padding: var(--space-4); }
  .login-page__signal { top: var(--space-4); left: var(--space-4); }
  .login-page__panel { padding: var(--space-6); }
  .login-page footer { align-items: flex-start; flex-direction: column; }
}
</style>
