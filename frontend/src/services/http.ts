import axios, { AxiosError, AxiosResponse } from "axios";

const http = axios.create({
  baseURL: "/api",
  timeout: 15000
});

http.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError<{ error?: { message?: string } }>) => {
    const message = error.response?.data?.error?.message ?? error.message;
    return Promise.reject(new Error(message));
  }
);

export default http;
