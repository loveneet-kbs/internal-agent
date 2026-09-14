import axios from "axios";

// Mutating routes require the admin token. Set VITE_ADMIN_TOKEN in frontend/.env
// to the same value as ADMIN_TOKEN in backend-python/.env.
//
// Note this token ships in the client bundle, so it is a guard against casual and
// cross-origin access, not a user identity. Swap it for real per-user auth before
// this is exposed to anyone you do not trust.
const ADMIN_TOKEN = import.meta.env.VITE_ADMIN_TOKEN ?? "";

const client = axios.create({
  baseURL: "/api",
  // The agent waits on an LLM round trip; 30s was short enough that a slow run
  // surfaced as "network error" while the task had actually succeeded.
  timeout: 90000,
  headers: ADMIN_TOKEN ? { Authorization: `Bearer ${ADMIN_TOKEN}` } : {}
});

/** Pull a readable message out of an axios failure. */
export function errorMessage(error, fallback = "Something went wrong.") {
  if (error?.code === "ECONNABORTED") {
    return "The request timed out. The task may still have completed — check Task History.";
  }
  return error?.response?.data?.error || fallback;
}

export const runAgent = (prompt) => client.post("/agent/run", { prompt });

export const getAvailableTools = () => client.get("/agent/tools");

export const getCustomers = () => client.get("/customers");

export const getCustomer = (id) => client.get(`/customers/${id}`);

export const createCustomer = (payload) => client.post("/customers", payload);

export const updateCustomer = (id, payload) => client.put(`/customers/${id}`, payload);

export const deleteCustomer = (id) => client.delete(`/customers/${id}`);

export const getTasks = () => client.get("/tasks");

export const getTask = (id) => client.get(`/tasks/${id}`);

export const deleteTask = (id) => client.delete(`/tasks/${id}`);

export const getApiActivity = () => client.get("/tasks/activity/recent");

export const getHealth = () => client.get("/health");

export const generateMail = (payload) => client.post("/mail/generate", payload);
export const sendMail = (payload) => client.post("/mail/send", payload);
export const getSentMail = () => client.get("/mail/sent");

export default client;

// --- profiles, teams, notes, recycle bin ---
export const searchCustomers = (params) => client.get("/customers/search", { params });
export const getCustomerStats = () => client.get("/customers/stats");
export const getDeletedCustomers = () => client.get("/customers/deleted");
export const restoreCustomer = (id) => client.post(`/customers/${id}/restore`);
export const getNotes = (id) => client.get(`/customers/${id}/notes`);
export const addNote = (id, body) => client.post(`/customers/${id}/notes`, { body, author: "you" });
export const deleteNote = (id, noteId) => client.delete(`/customers/${id}/notes/${noteId}`);

// --- leave ---
export const getLeaveRequests = (params) => client.get("/leave", { params });
export const approveLeave = (id, note) => client.post(`/leave/${id}/approve`, { note });
export const rejectLeave = (id, note) => client.post(`/leave/${id}/reject`, { note });

// --- attendance ---
export const getAttendance = (params) => client.get("/attendance", { params });
export const getAttendanceSummary = (day) => client.get("/attendance/summary", { params: { day } });
export const markAttendance = (payload) => client.post("/attendance", payload);

// --- work tasks + snapshot ---
export const getWorkTasks = (params) => client.get("/work-tasks", { params });
export const getTaskSummary = (params) => client.get("/work-tasks/summary", { params });
export const createWorkTask = (payload) => client.post("/work-tasks", payload);
export const updateWorkTask = (id, payload) => client.put(`/work-tasks/${id}`, payload);
export const completeWorkTask = (id) => client.post(`/work-tasks/${id}/complete`);
export const getSnapshot = (id) => client.get(`/customers/${id}/snapshot`);

// --- meetings & calendar ---
export const getMeetings = (params) => client.get("/meetings", { params });
export const getMeeting = (id) => client.get(`/meetings/${id}`);
export const createMeeting = (payload) => client.post("/meetings", payload);
export const cancelMeeting = (id, payload) => client.post(`/meetings/${id}/cancel`, payload);
export const getFreeSlots = (params) => client.get("/meetings/slots", { params });

// --- analytics & anomaly radar ---
export const getAnomalies = () => client.get("/analytics/anomalies");
export const getChartData = (params) => client.get("/analytics/charts", { params });

