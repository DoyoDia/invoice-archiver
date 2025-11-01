import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { getAuthToken } from "../utils/authToken";

const http = axios.create({
  baseURL: "/api",
  timeout: 15000
});

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAuthToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError<{ error?: { message?: string } }>) => {
    const message = error.response?.data?.error?.message ?? error.message;
    return Promise.reject(new Error(message));
  }
);

export default http;
