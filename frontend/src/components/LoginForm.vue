<script setup>
import { ref } from 'vue'

const props = defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['submit'])

const username = ref('')
const password = ref('')
const showPassword = ref(false)

const handleSubmit = () => {
  emit('submit', {
    username: username.value.trim(),
    password: password.value,
  })
}
</script>

<template>
  <form class="login-card" @submit.prevent="handleSubmit">
    <h1>管理后台登录</h1>
    <p class="login-subtitle">请输入账户信息以继续</p>

    <label class="login-field">
      <span>用户名</span>
      <input
        v-model="username"
        type="text"
        name="username"
        placeholder="输入用户名"
        autocomplete="username"
        required
      />
    </label>

    <label class="login-field">
      <span>密码</span>
      <div class="password-input">
        <input
          v-model="password"
          :type="showPassword ? 'text' : 'password'"
          name="password"
          placeholder="输入密码"
          autocomplete="current-password"
          required
        />
        <button type="button" class="password-toggle" aria-label="切换密码可见性" @click="showPassword = !showPassword">
          {{ showPassword ? '隐藏' : '显示' }}
        </button>
      </div>
    </label>

    <p v-if="error" class="login-error">{{ error }}</p>

    <button class="login-submit" type="submit" :disabled="loading">
      <span v-if="loading">登录中...</span>
      <span v-else>登录</span>
    </button>
  </form>
</template>
