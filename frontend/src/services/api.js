import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail;
    if (detail && !error.message) {
      error.message = typeof detail === 'string' ? detail : JSON.stringify(detail);
    } else if (detail) {
      error.message = typeof detail === 'string' ? detail : JSON.stringify(detail);
    }
    return Promise.reject(error);
  },
);

export default api;
