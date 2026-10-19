import { request } from './client.js';

const toUser = (response) => {
  const user = response?.user ?? response;
  return user ? { name: user.name || user.username || '', email: user.email || '', is_staff: Boolean(user.is_staff), must_change_password: Boolean(user.must_change_password) } : null;
};

export async function login(username, password) {
  return toUser(await request('POST', '/login/', {
    json: { username, password }, silentUnauthorized: true,
  }));
}

export async function logout() {
  await request('POST', '/logout/');
}

export async function getMe() {
  return toUser(await request('GET', '/session/', { silentUnauthorized: true }));
}

export async function updateMe(data) {
  return toUser(await request('PATCH', '/account/', { json: data }));
}

export const changePassword = (currentPassword, newPassword) =>
  request('POST', '/account/password/', { json: { currentPassword, newPassword } });
