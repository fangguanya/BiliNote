import request from '@/utils/request'

// BaiduPCS-Py API 接口
export const baidupcsApi = {
  // 添加用户（相当于原来的useradd命令）
  addUser: async (data: { user_name?: string, cookies?: string, bduss?: string }) => {
    return request.post('/baidupcs/add_user', data)
  },
  
  // 移除用户
  removeUser: async (data: { user_name?: string }) => {
    return request.post('/baidupcs/remove_user', data)
  },
  
  // 获取用户列表
  getUsers: async () => {
    return request.get('/baidupcs/users')
  },
  
  // 检查认证状态
  getAuthStatus: async () => {
    return request.get('/baidupcs/auth_status')
  },
  
  // 获取文件列表
  getFileList: async (params: { path?: string, user_name?: string } = {}) => {
    return request.get('/baidupcs/file_list', { params })
  },
  
  // 获取使用指南
  getUsageGuide: async () => {
    return request.get('/baidupcs/usage_guide')
  },
}

 