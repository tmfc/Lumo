const normalizeBaseUrl = (value, fallback) => {
  const base = value || fallback
  return base.endsWith('/') ? base : `${base}/`
}

const DOCUMENT_API_BASE_URL = normalizeBaseUrl(
  import.meta.env?.VITE_DOC_API_BASE_URL ||
    import.meta.env?.VITE_API_BASE_URL ||
    'http://localhost:8000/api/documents/',
  'http://localhost:8000/api/documents/'
)

const AUTH_API_BASE_URL = normalizeBaseUrl(
  import.meta.env?.VITE_AUTH_API_BASE_URL ||
    import.meta.env?.VITE_API_AUTH_BASE_URL ||
    'http://localhost:8000/api/auth/',
  'http://localhost:8000/api/auth/'
)

const unauthorizedError = () => {
  const error = new Error('UNAUTHORIZED')
  error.status = 401
  return error
}

const parseJson = async (response) => {
  const text = await response.text()
  if (!text) return {}
  try {
    return JSON.parse(text)
  } catch (err) {
    console.error('解析响应失败', err)
    return {}
  }
}

const handleResponse = async (response, defaultMessage = '请求失败') => {
  if (response.status === 401) {
    throw unauthorizedError()
  }
  const data = await parseJson(response)
  if (!response.ok) {
    throw new Error(data.error || data.detail || defaultMessage)
  }
  return data
}

let authToken = ''

export const setAuthToken = (token) => {
  authToken = token || ''
}

const withAuthHeaders = (headers = {}) => {
  const nextHeaders = { ...headers }
  if (authToken) {
    nextHeaders.Authorization = `Token ${authToken}`
  }
  return nextHeaders
}

export const documentApi = {
  async getDocuments(params = {}) {
    const query = new URLSearchParams(params)
    const queryString = query.toString()
    const url = queryString ? `${DOCUMENT_API_BASE_URL}?${queryString}` : DOCUMENT_API_BASE_URL
    const response = await fetch(url, {
      headers: withAuthHeaders(),
    })
    return handleResponse(response, '获取文档列表失败')
  },

  async getDocument(id) {
    if (!id && id !== 0) {
      throw new Error('缺少文档 ID')
    }

    const response = await fetch(`${DOCUMENT_API_BASE_URL}${id}/`, {
      headers: withAuthHeaders(),
    })
    return handleResponse(response, '获取文档详情失败')
  },

  uploadDocument(file, { onProgress } = {}) {
    return new Promise((resolve, reject) => {
      const formData = new FormData()
      formData.append('file', file)

      const xhr = new XMLHttpRequest()
      xhr.open('POST', DOCUMENT_API_BASE_URL, true)
      if (authToken) {
        xhr.setRequestHeader('Authorization', `Token ${authToken}`)
      }

      if (xhr.upload && typeof onProgress === 'function') {
        xhr.upload.onprogress = (event) => {
          if (!event.lengthComputable) return
          const percent = Math.round((event.loaded / event.total) * 100)
          onProgress(percent)
        }
      }

      xhr.onerror = () => {
        reject(new Error('上传失败，请检查网络连接'))
      }

      xhr.onload = () => {
        if (xhr.status === 401) {
          const error = unauthorizedError()
          reject(error)
          return
        }

        const contentType = xhr.getResponseHeader('Content-Type') || ''
        const isJson = contentType.includes('application/json')

        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(isJson ? JSON.parse(xhr.responseText || '{}') : {})
          return
        }

        let message = '上传失败'
        if (isJson && xhr.responseText) {
          try {
            const error = JSON.parse(xhr.responseText)
            message = error.file?.[0] || error.error || error.detail || message
          } catch (err) {
            console.error('解析上传错误响应失败', err)
          }
        }
        reject(new Error(message))
      }

      xhr.send(formData)
    })
  },

  async deleteDocument(id) {
    const response = await fetch(`${DOCUMENT_API_BASE_URL}${id}/`, {
      method: 'DELETE',
      headers: withAuthHeaders(),
    })
    if (response.status === 401) {
      throw unauthorizedError()
    }
    if (!response.ok) {
      throw new Error('删除文档失败')
    }
    return true
  },

  async reprocessDocument(id) {
    const response = await fetch(`${DOCUMENT_API_BASE_URL}${id}/reprocess/`, {
      method: 'POST',
      headers: withAuthHeaders(),
    })
    return handleResponse(response, '重新处理失败')
  },
}

export const authApi = {
  async login({ username, password }) {
    const response = await fetch(`${AUTH_API_BASE_URL}login/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username, password }),
    })
    return handleResponse(response, '登录失败')
  },

  async logout() {
    const response = await fetch(`${AUTH_API_BASE_URL}logout/`, {
      method: 'POST',
      headers: withAuthHeaders({
        'Content-Type': 'application/json',
      }),
    })
    if (response.status === 401) {
      return {}
    }
    return handleResponse(response, '退出失败')
  },
}
