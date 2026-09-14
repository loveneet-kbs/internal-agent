import StatusBadge from "./StatusBadge.jsx";
import EmailApproval from "./EmailApproval.jsx";
import { PackageCheck } from "lucide-react";
import {
  SnapshotView,
  TaskSummaryView,
  WorkTasksView,
  AttendanceSummaryView,
  AttendanceView,
  LeaveRow,
  LeaveView,
  MailView,
  NotesView,
  ObjectView,
  PeopleView,
  PersonView,
  RowsView,
  StatsView,
  AnomalyRadarView,
  ChartView,
  MeetingView,
  MeetingListView,
  FreeSlotsView,
  shapeOf
} from "./ResultViews.jsx";

/** Renders one tool's result in whatever form actually reads as an answer. */
function ResultBody({ result, onMailSent, onOpenProfile, onDecideLeave, onCompleteTask, onRunPrompt }) {
  const data = result?.data;

  switch (shapeOf(result)) {
    case "anomalies":
      return <AnomalyRadarView data={data} onRunPrompt={onRunPrompt} />;
    case "chart":
      return <ChartView data={data} />;
    case "meeting":
      return <MeetingView meeting={data} onOpenProfile={onOpenProfile} />;
    case "meetings":
      return <MeetingListView rows={data} onOpenProfile={onOpenProfile} />;
    case "free-slots":
      return <FreeSlotsView data={data} onScheduleSlot={onRunPrompt} />;
    case "snapshot":
      return <SnapshotView data={data} onOpenProfile={onOpenProfile} />;
    case "work-tasks":
      return (
        <WorkTasksView rows={data} onComplete={onCompleteTask} onOpenProfile={onOpenProfile} />
      );
    case "work-task":
      return (
        <WorkTasksView rows={[data]} onComplete={onCompleteTask} onOpenProfile={onOpenProfile} />
      );
    case "task-summary":
      return <TaskSummaryView data={data} />;
    case "attendance":
      return <AttendanceView rows={data} onOpenProfile={onOpenProfile} />;
    case "attendance-one":
      return <AttendanceView rows={[data]} onOpenProfile={onOpenProfile} />;
    case "attendance-summary":
      return <AttendanceSummaryView data={data} onOpenProfile={onOpenProfile} />;
    case "leave":
      return <LeaveView rows={data} onDecide={onDecideLeave} onOpenProfile={onOpenProfile} />;
    case "leave-one":
      return (
        <ul>
          <LeaveRow request={data} onDecide={onDecideLeave} onOpenProfile={onOpenProfile} />
        </ul>
      );
    case "people":
      return <PeopleView rows={data} onOpenProfile={onOpenProfile} />;
    case "person":
      return <PersonView person={data} onOpenProfile={onOpenProfile} />;
    case "notes":
      return <NotesView rows={data} />;
    case "mail":
      return <MailView rows={data} />;
    case "stats":
      return <StatsView data={data} />;
    case "draft":
      return <EmailApproval draft={data} onSent={onMailSent} />;
    case "rows":
      return <RowsView rows={data} />;
    case "object":
      return <ObjectView data={data} />;
    case "empty-list":
      return <p className="text-sm text-muted">Nothing matched.</p>;
    default:
      return null;
  }
}

export default function ResultPanel({
  task,
  result,
  executed = [],
  onMailSent,
  onOpenProfile,
  onDecideLeave,
  onCompleteTask,
  onRunPrompt
}) {
  if (!task) {
    return (
      <div className="glass rounded-2xl p-5">
        <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold tracking-wide text-text">
          <PackageCheck size={15} className="text-accent" /> RESULT
        </h2>
        <p className="text-sm text-muted">Results will appear here after you run a task.</p>
      </div>
    );
  }

  // A multi-step run produces one result per tool. Show them all, in order -
  // otherwise "who is on leave, then email them" silently drops the list.
  const steps = executed.length > 0 ? executed : result ? [{ tool: task.tool_name, result }] : [];
  const isChain = steps.length > 1;

  return (
    <div className="glass animate-fade-in rounded-2xl p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-text">
          <PackageCheck size={15} className="text-accent" /> RESULT
          {isChain && (
            <span className="glass rounded-full px-2 py-0.5 font-mono text-[10px] text-muted">
              {steps.length} steps
            </span>
          )}
        </h2>
        <StatusBadge status={task.status} />
      </div>

      {task.status === "failed" || task.status === "unsupported" ? (
        <div className="rounded-xl border border-danger/30 bg-danger/8 p-4 text-sm">
          <p className="font-semibold text-danger">Something went wrong while running this task.</p>
          <p className="mt-1 text-text-2">{task.error || "Unknown error."}</p>
        </div>
      ) : task.status === "needs_information" ? (
        <div className="rounded-xl border border-warning/30 bg-warning/8 p-4 text-sm">
          <p className="font-semibold text-warning">I need a bit more information.</p>
          <p className="mt-1 text-text-2">{task.error}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* The model's closing text is deliberately NOT rendered. It restates
              what the step views already show - typically dumping the whole email
              body above the approval card that renders it properly. Each step
              speaks for itself. */}
          {steps.map((step, index) => (
            <section key={`${step.tool}-${index}`} className="space-y-2">
              {isChain && (
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-accent/15 font-mono text-[10px] font-semibold text-accent">
                    {index + 1}
                  </span>
                  <span className="font-mono text-xs text-accent">{step.tool}</span>
                  {step.duration_ms != null && (
                    <span className="font-mono text-[10px] text-muted">{step.duration_ms}ms</span>
                  )}
                  <span className="h-px flex-1 bg-line/25" />
                </div>
              )}
              {step.result?.message && (
                <p className="text-sm font-medium text-text-2">{step.result.message}</p>
              )}
              <ResultBody
                result={step.result}
                onMailSent={onMailSent}
                onOpenProfile={onOpenProfile}
                onDecideLeave={onDecideLeave}
                onCompleteTask={onCompleteTask}
                onRunPrompt={onRunPrompt}
              />
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
