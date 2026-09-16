import axios from 'axios'

const http = axios.create({ baseURL: '/api' })

export function createLinks(formData) {
  return http.post('/links', formData)
}

export function listLinks() {
  return http.get('/links')
}

export function shareLink(token) {
  return http.post(`/links/${token}/share`)
}

export function burnLink(token) {
  return http.post(`/links/${token}/burn`)
}
