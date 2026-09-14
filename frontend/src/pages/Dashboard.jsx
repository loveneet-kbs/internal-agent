import { useEffect, useState, useCallback, useRef } from "react";
import Header from "../components/Header.jsx";
import Sidebar from "../components/Sidebar.jsx";
import PromptBox from "../components/PromptBox.jsx";
import TaskExecution from "../components/TaskExecution.jsx";
import ResultPanel from "../components/ResultPanel.jsx";
import TaskHistory from "../components/TaskHistory.jsx";
import ApiActivity from "../components/ApiActivity.jsx";
import CustomerTable from "../components/CustomerTable.jsx";
import LoadingState from "../components/LoadingState.jsx";
import * as api from "../services/api.js";
import { Users, ListChecks, Activity as ActivityIcon, CalendarClock, Calendar } from "lucide-react";
import MailStudio from "../components/MailStudio.jsx";
import TeamsOverview from "../components/TeamsOverview.jsx";
import LeaveBoard from "../components/LeaveBoard.jsx";
import TaskBoard from "../components/TaskBoard.jsx";
import AttendanceBoard from "../components/AttendanceBoard.jsx";
import CustomerProfile from "../components/CustomerProfile.jsx";
import SentMail from "../components/SentMail.jsx";
import MeetingsBoard from "../components/MeetingsBoard.jsx";

const PROGRESS_MESSAGES = [
  { label: "AI is analyzing your request...", stage: 1 },
  { label: "Selecting tool...", stage: 2 },
  { label: "Executing tool...", stage: 3 }
];

// Must match the PIPELINE array in TaskExecution.jsx.
const PIPELINE_LENGTH = 6;

// `tool_name` is a comma-joined chain for multi-step runs ("create_customer,
// draft_email"), so this substring-matches rather than comparing whole strings.
const MUTATING_TOOLS = [
  "create_customer",
  "create_customers_bulk",
  "update_customer",
  "delete_customer",
  "restore_customer",
  "add_note"
];

const touchedRecords = (toolName = "") =>
  MUTATING_TOOLS.some((tool) => toolName.includes(tool));

export default function Dashboard() {
  const [view, setView] = useState("dashboard");
  const [connected, setConnected] = useState(false);

  const [isRunning, setIsRunning] = useState(false);
  const [steps, setSteps] = useState([]);
  const [activeStage, setActiveStage] = useState(-1);
  const [lastTask, setLastTask] = useState(null);
  const [lastResult, setLastResult] = useState(null);
  const [lastExecuted, setLastExecuted] = useState([]);

  const [tasks, setTasks] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [activity, setActivity] = useState([]);
  const [tools, setTools] = useState([]);
  const [sentMail, setSentMail] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [customersLoading, setCustomersLoading] = useState(false);
  const [stats, setStats] = useState(null);
  const [leaveSummary, setLeaveSummary] = useState(null);
  const [profileId, setProfileId] = useState(null);

  const refreshCustomers = useCallback(async () => {
    setCustomersLoading(true);
    try {
      const { data } = await api.getCustomers();
      setCustomers(data.data);
      const { data: statsBody } = await api.getCustomerStats();
      setStats(statsBody.data);
      const { data: leaveBody } = await api.getLeaveRequests({ status: "pending" });
      setLeaveSummary(leaveBody.summary);
    } catch (e) {
      // Non-fatal: surface via console, table just stays empty
      console.error(e);
    } finally {
      setCustomersLoading(false);
    }
  }, []);

  const refreshTasks = useCallback(async () => {
    try {
      const { data } = await api.getTasks();
      setTasks(data.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const refreshActivity = useCallback(async () => {
    try {
      const { data } = await api.getApiActivity();
      setActivity(data.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const refreshSentMail = useCallback(async () => {
    try {
      const { data } = await api.getSentMail();
      setSentMail(data.data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const refreshMeetings = useCallback(async () => {
    try {
      const { data } = await api.getMeetings();
      setMeetings(data.data || []);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    api
      .getHealth()
      .then(() => setConnected(true))
      .catch(() => setConnected(false));
    refreshCustomers();
    refreshTasks();
    refreshActivity();
    refreshSentMail();
    refreshMeetings();
    api.getAvailableTools().then(({ data }) => setTools(data.data)).catch(() => {});
  }, [refreshCustomers, refreshTasks, refreshActivity, refreshSentMail, refreshMeetings]);

  // Cleared on unmount so an in-flight run cannot set state on a gone component.
  // Decide a leave request straight from a result card, then refresh so the
  // directory reflects any status change the approval caused.
  const handleDecideLeave = useCallback(
    async (request, approve, note) => {
      if (approve) await api.approveLeave(request.id, note);
      else await api.rejectLeave(request.id, note);
      await refreshCustomers();
    },
    [refreshCustomers]
  );

  const handleCompleteTask = useCallback(async (task) => {
    await api.completeWorkTask(task.id);
  }, []);

  const timersRef = useRef([]);
  useEffect(() => () => timersRef.current.forEach(clearTimeout), []);

  const handleRun = async (prompt) => {
    setIsRunning(true);
    setLastTask(null);
    setLastResult(null);
    setLastExecuted([]);
    setActiveStage(0);
    setSteps([{ label: "Prompt received", status: "completed" }]);

    // Progressive UI feedback while the real request is in flight.
    timersRef.current.forEach(clearTimeout);
    timersRef.current = PROGRESS_MESSAGES.map((m, i) =>
      setTimeout(() => {
        setActiveStage(m.stage);
        setSteps((prev) => [...prev, { label: m.label, status: "running" }]);
      }, (i + 1) * 500)
    );

    try {
      const { data } = await api.runAgent(prompt);
      timersRef.current.forEach(clearTimeout);

      setSteps(data.steps || []);
      // Updater form: reading `activeStage` directly captured the value from the
      // render that created this handler, never what the timers above had set.
      setActiveStage((prev) => (data.success ? PIPELINE_LENGTH - 1 : Math.min(3, prev)));
      setLastTask(data.task);
      setLastResult(data.result);
      setLastExecuted(data.executed || []);

      refreshTasks();
      refreshActivity();
      if (touchedRecords(data.task?.tool_name ?? "")) {
        refreshCustomers();
      }
    } catch (err) {
      timersRef.current.forEach(clearTimeout);
      const message = api.errorMessage(err, "Network error while reaching the backend.");
      setSteps((prev) => [...prev, { label: "Request failed", status: "failed", detail: message }]);
      setLastTask({ status: "failed", error: message, prompt });
      setLastResult(null);
      setLastExecuted([]);
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="flex h-screen flex-col">
      <Header connected={connected} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar active={view} onChange={setView} />
        <main className="scrollbar-thin flex-1 overflow-y-auto p-4 pb-24 sm:p-6 md:pb-6">
          {view === "dashboard" && (
            <div className="mx-auto flex max-w-6xl flex-col gap-5">
              <div className="flex flex-wrap items-end justify-between gap-3 px-1">
                <div>
                  <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.24em] text-accent/80">Workspace overview</p>
                  <h2 className="text-2xl font-semibold tracking-tight text-text">Command your employee data</h2>
                  <p className="mt-1 text-sm text-muted">Turn a plain-English request into a verified employee-data action.</p>
                </div>
                <div className="flex items-center gap-2 rounded-lg glass px-3 py-2 font-mono text-xs text-muted">
                  <span className="h-1.5 w-1.5 rounded-full bg-success" />
                  Live workspace
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Metric icon={Users} label="Employees" value={customers.length} tone="text-info" onClick={() => setView("customers")} />
                <Metric icon={ListChecks} label="Tasks tracked" value={tasks.length} tone="text-accent" onClick={() => setView("tasks")} />
                <Metric icon={Calendar} label="Meetings" value={meetings.length} tone="text-success" onClick={() => setView("meetings")} />
                <Metric icon={CalendarClock} label="Pending leave" value={leaveSummary?.pending ?? 0} tone="text-warning" onClick={() => setView("leave")} />
              </div>
              <PromptBox onRun={handleRun} onOpenMail={() => setView("mail")} isRunning={isRunning} />
              <TaskExecution steps={steps} activeStage={activeStage} isRunning={isRunning} />
              <ResultPanel
                task={lastTask}
                result={lastResult}
                executed={lastExecuted}
                onMailSent={refreshSentMail}
                onOpenProfile={setProfileId}
                onDecideLeave={handleDecideLeave}
                onCompleteTask={handleCompleteTask}
                onRunPrompt={handleRun}
              />
              <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
                <TaskHistory tasks={tasks} onRefresh={refreshTasks} />
                <ApiActivity activity={activity} />
              </div>
            </div>
          )}

          {view === "tasks" && (
            <div className="mx-auto max-w-4xl">
              <TaskHistory tasks={tasks} onRefresh={refreshTasks} />
            </div>
          )}

          {view === "meetings" && (
            <MeetingsBoard onOpenProfile={setProfileId} />
          )}

          {view === "customers" && (
            <div className="mx-auto max-w-5xl">
              {customersLoading && customers.length === 0 ? (
                  <LoadingState label="Loading employees..." />
              ) : (
                <CustomerTable
                  customers={customers}
                  onRefresh={refreshCustomers}
                  isLoading={customersLoading}
                  onOpenProfile={setProfileId}
                />
              )}
            </div>
          )}

          {view === "activity" && (
            <div className="mx-auto max-w-3xl">
              <ApiActivity activity={activity} />
            </div>
          )}

          {view === "settings" && (
            <div className="mx-auto max-w-3xl glass rounded-2xl p-5">
              <h2 className="mb-3 text-sm font-semibold tracking-wide text-text-2">
                REGISTERED TOOLS
              </h2>
              <p className="mb-4 text-sm text-muted">
                The AI agent may only select from these tools — nothing else is executable.
              </p>
              <ul className="space-y-2">
                {tools.map((t) => (
                  <li
                    key={t.name}
                    className="rounded-xl border border-line/25 bg-glass/25 px-3 py-2.5 transition-colors hover:bg-glass/40"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm text-accent">{t.name}</span>
                      <span className="font-mono text-xs text-muted">
                        {t.method} {t.endpoint}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted">{t.description}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {view === "teams" && (
            <TeamsOverview customers={customers} stats={stats} onOpenProfile={setProfileId} />
          )}

          {view === "work" && <TaskBoard onOpenProfile={setProfileId} />}

          {view === "attendance" && (
            <AttendanceBoard customers={customers} onOpenProfile={setProfileId} />
          )}

          {view === "leave" && (
            <LeaveBoard onOpenProfile={setProfileId} onDecided={refreshCustomers} />
          )}

          {view === "mail" && <MailStudio customers={customers} onSent={refreshSentMail} />}

          {view === "sent-mail" && <SentMail messages={sentMail} />}
        </main>
      </div>

      {profileId && (
        <CustomerProfile
          customerId={profileId}
          onClose={() => setProfileId(null)}
          onEmail={(person) => {
            setProfileId(null);
            setView("dashboard");
            handleRun(`Draft an email to ${person.name}`);
          }}
        />
      )}
    </div>
  );
}

function Metric({ icon: Icon, label, value, tone, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="glass glass-hover group flex items-center gap-3 rounded-2xl px-4 py-3.5 text-left"
    >
      <Icon size={17} className={tone} />
      <div>
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted">{label}</p>
        <p className="mt-0.5 text-lg font-semibold text-text group-hover:text-accent">{value}</p>
      </div>
    </button>
  );
}
