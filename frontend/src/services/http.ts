import axios, { AxiosError, AxiosResponse } from "axios";

const http = axios.create({
  baseURL: "/api",
  timeout: 60000
});

http.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError<{ detail?: string }>) => {
    const message = error.response?.data?.detail ?? error.message;
    return Promise.reject(new Error(message));
  }
);

export default http;
