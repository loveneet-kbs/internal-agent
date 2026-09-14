import { useEffect, useState, useMemo, useCallback } from "react";
import {
  Calendar as CalendarIcon,
  Clock,
  Video,
  Users,
  Plus,
  ChevronLeft,
  ChevronRight,
  Filter,
  X,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  CalendarCheck,
  Search,
  Trash2
} from "lucide-react";
import * as api from "../services/api.js";
import { Avatar, TeamBadge } from "./TeamBadge.jsx";

const TEAMS = ["All", "AI", "Development", "Design", "QA", "Product"];

function formatTime(isoString) {
  if (!isoString) return "";
  const dt = new Date(isoString.replace(" ", "T"));
  if (Number.isNaN(dt.getTime())) return isoString;
  return dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// A bare "YYYY-MM-DD" is parsed by `new Date()` as UTC midnight, not local
// midnight - rendering it back in a local timezone can land on the wrong
// day. Build the Date from its parts instead so it always stays local.
function localDateFromIso(isoDate) {
  const [y, m, d] = (isoDate || "").split("-").map(Number);
  return new Date(y || 1970, (m || 1) - 1, d || 1);
}

function formatDateHeader(isoDate) {
  const dt = localDateFromIso(isoDate);
  if (Number.isNaN(dt.getTime())) return isoDate;
  return dt.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}

// The inverse of localDateFromIso: a calendar Date's own YYYY-MM-DD in local
// time. `date.toISOString()` must never be used for this - it converts to
// UTC first, which silently shifts the date by a day in most timezones.
function toLocalIsoDate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export default function MeetingsBoard({ onOpenProfile }) {
  const [meetings, setMeetings] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedTeam, setSelectedTeam] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState("month"); // 'month' | 'week' | 'agenda'
  const [currentDate, setCurrentDate] = useState(new Date());

  // Modal states
  const [showModal, setShowModal] = useState(false);
  const [showSlotFinder, setShowSlotFinder] = useState(false);
  const [selectedDateForNew, setSelectedDateForNew] = useState(null);
  const [selectedDayDetail, setSelectedDayDetail] = useState(null);

  const fetchMeetings = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.getMeetings();
      setMeetings(data.data || []);
    } catch (err) {
      console.error("Failed to fetch meetings", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMeetings();
    api.getCustomers().then(({ data }) => setCustomers(data.data || [])).catch(() => {});
  }, [fetchMeetings]);

  const handleCancelMeeting = async (meetingId) => {
    if (!window.confirm("Are you sure you want to cancel this meeting?")) return;
    try {
      await api.cancelMeeting(meetingId, { reason: "Cancelled by user via Calendar" });
      fetchMeetings();
    } catch (err) {
      alert(api.errorMessage(err, "Failed to cancel meeting."));
    }
  };

  // Filter meetings
  const filteredMeetings = useMemo(() => {
    return meetings.filter((m) => {
      if (selectedTeam !== "All" && m.team?.toLowerCase() !== selectedTeam.toLowerCase()) {
        return false;
      }
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const inTitle = m.title?.toLowerCase().includes(query);
        const inHost = m.host_name?.toLowerCase().includes(query);
        const inDesc = m.description?.toLowerCase().includes(query);
        const inAtt = m.attendees?.some((a) => (typeof a === "object" ? a.name : a)?.toLowerCase().includes(query));
        if (!inTitle && !inHost && !inDesc && !inAtt) return false;
      }
      return true;
    });
  }, [meetings, selectedTeam, searchQuery]);

  // Calendar month matrix calculation
  const calendarDays = useMemo(() => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();

    const firstDayIndex = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const daysInPrevMonth = new Date(year, month, 0).getDate();

    const days = [];

    // Prev month overflow
    for (let i = firstDayIndex - 1; i >= 0; i--) {
      const d = new Date(year, month - 1, daysInPrevMonth - i);
      days.push({ date: d, isCurrentMonth: false });
    }

    // Current month days
    for (let i = 1; i <= daysInMonth; i++) {
      const d = new Date(year, month, i);
      days.push({ date: d, isCurrentMonth: true });
    }

    // Next month overflow to complete 35 or 42 grid
    const remaining = (7 - (days.length % 7)) % 7;
    for (let i = 1; i <= remaining; i++) {
      const d = new Date(year, month + 1, i);
      days.push({ date: d, isCurrentMonth: false });
    }

    return days;
  }, [currentDate]);

  // Group meetings by YYYY-MM-DD
  const meetingsByDate = useMemo(() => {
    const map = {};
    for (const m of filteredMeetings) {
      if (m.status === "cancelled") continue;
      const dateKey = m.start_time?.split("T")[0];
      if (dateKey) {
        if (!map[dateKey]) map[dateKey] = [];
        map[dateKey].push(m);
      }
    }
    return map;
  }, [filteredMeetings]);

  const monthName = currentDate.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const todayIso = toLocalIsoDate(new Date());

  const handlePrevMonth = () => {
    setCurrentDate((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1));
  };
  const handleNextMonth = () => {
    setCurrentDate((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1));
  };
  const handleToday = () => {
    setCurrentDate(new Date());
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/15 text-accent">
              <CalendarIcon size={16} />
            </span>
            <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-accent">Workspace Calendar</p>
          </div>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight text-text">Scheduled Team Meetings</h2>
          <p className="mt-0.5 text-xs text-muted">View synchronized team availability, schedule events, and resolve meeting clashes.</p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => setShowSlotFinder(true)}
            className="flex items-center gap-2 rounded-xl border border-line/30 bg-glass/30 px-3.5 py-2 text-xs font-medium text-text-2 transition hover:bg-glass/60 hover:text-text"
          >
            <Sparkles size={14} className="text-accent" />
            Check Free Slots
          </button>

          <button
            type="button"
            onClick={() => {
              setSelectedDateForNew(todayIso);
              setShowModal(true);
            }}
            className="flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-xs font-medium text-white shadow-lg shadow-accent/25 transition hover:bg-accent/90"
          >
            <Plus size={15} />
            Schedule Meeting
          </button>
        </div>
      </div>

      {/* Control bar: Team filters + Search + Month Nav + View Switcher */}
      <div className="glass flex flex-wrap items-center justify-between gap-3 rounded-2xl p-3">
        {/* Teams filter */}
        <div className="flex flex-wrap items-center gap-1.5">
          {TEAMS.map((t) => {
            const active = selectedTeam === t;
            return (
              <button
                key={t}
                type="button"
                onClick={() => setSelectedTeam(t)}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                  active
                    ? "bg-accent text-white shadow-sm"
                    : "text-muted hover:bg-glass/50 hover:text-text"
                }`}
              >
                {t}
              </button>
            );
          })}
        </div>

        {/* Search */}
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search meetings, attendees..."
            className="w-full rounded-lg border border-line/25 bg-background/50 py-1.5 pl-8 pr-3 text-xs text-text placeholder-muted focus:border-accent focus:outline-none"
          />
        </div>

        {/* Month Navigator & View Switcher */}
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg border border-line/25 bg-background/40 p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("month")}
              className={`rounded px-2.5 py-1 text-xs font-medium transition ${
                viewMode === "month" ? "bg-glass text-accent shadow-sm" : "text-muted hover:text-text"
              }`}
            >
              Month
            </button>
            <button
              type="button"
              onClick={() => setViewMode("agenda")}
              className={`rounded px-2.5 py-1 text-xs font-medium transition ${
                viewMode === "agenda" ? "bg-glass text-accent shadow-sm" : "text-muted hover:text-text"
              }`}
            >
              Agenda
            </button>
          </div>

          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={handlePrevMonth}
              className="rounded-lg p-1.5 text-muted hover:bg-glass hover:text-text"
              title="Previous month"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="min-w-[130px] text-center font-medium text-xs text-text">{monthName}</span>
            <button
              type="button"
              onClick={handleNextMonth}
              className="rounded-lg p-1.5 text-muted hover:bg-glass hover:text-text"
              title="Next month"
            >
              <ChevronRight size={16} />
            </button>
            <button
              type="button"
              onClick={handleToday}
              className="ml-1 rounded-lg border border-line/25 px-2 py-1 text-[11px] font-mono text-muted hover:bg-glass hover:text-text"
            >
              Today
            </button>
          </div>
        </div>
      </div>

      {/* Main Views */}
      {viewMode === "month" && (
        <div className="glass overflow-hidden rounded-2xl border border-line/25">
          {/* Weekday headers */}
          <div className="grid grid-cols-7 border-b border-line/25 bg-glass/50 text-center font-mono text-[11px] uppercase tracking-wider text-muted">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => (
              <div key={day} className="py-2.5">
                {day}
              </div>
            ))}
          </div>

          {/* Days Grid */}
          <div className="grid grid-cols-7 divide-x divide-y divide-line/20">
            {calendarDays.map(({ date, isCurrentMonth }, idx) => {
              const iso = toLocalIsoDate(date);
              const isToday = iso === todayIso;
              const dayMeetings = meetingsByDate[iso] || [];

              return (
                <div
                  key={idx}
                  onClick={() => setSelectedDayDetail(iso)}
                  className={`group min-h-[110px] cursor-pointer p-2 transition-colors ${
                    isCurrentMonth ? "bg-background/20" : "bg-background/5 opacity-40"
                  } ${isToday ? "bg-accent/5 ring-1 ring-inset ring-accent/30" : ""} hover:bg-glass/30`}
                  title="View everything scheduled this day"
                >
                  <div className="flex items-center justify-between">
                    <span
                      className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-medium ${
                        isToday ? "bg-accent text-white" : "text-text-2"
                      }`}
                    >
                      {date.getDate()}
                    </span>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedDateForNew(iso);
                        setShowModal(true);
                      }}
                      className="opacity-0 group-hover:opacity-100 rounded p-0.5 text-muted hover:bg-glass hover:text-accent"
                      title="Schedule on this date"
                    >
                      <Plus size={12} />
                    </button>
                  </div>

                  {/* Day meetings chips */}
                  <div className="mt-1.5 space-y-1">
                    {dayMeetings.slice(0, 3).map((m) => (
                      <div
                        key={m.id}
                        className="group/chip relative truncate rounded-md border border-line/30 bg-glass/60 px-1.5 py-0.5 text-[10px] text-text transition hover:border-accent/50 hover:bg-accent/15"
                      >
                        <div className="flex items-center gap-1 truncate">
                          <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-accent" />
                          <span className="font-mono text-[9px] text-muted">{formatTime(m.start_time)}</span>
                          <span className="truncate font-medium">{m.title}</span>
                        </div>
                      </div>
                    ))}

                    {dayMeetings.length > 3 && (
                      <p className="text-center font-mono text-[9px] text-accent">
                        +{dayMeetings.length - 3} more
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {viewMode === "agenda" && (
        <div className="space-y-4">
          {filteredMeetings.length === 0 ? (
            <div className="glass rounded-2xl p-12 text-center text-muted">
              <CalendarIcon size={32} className="mx-auto mb-2 opacity-40" />
              <p className="text-sm">No meetings scheduled matching your filters.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {filteredMeetings.map((m) => {
                const isCancelled = m.status === "cancelled";
                return (
                  <div
                    key={m.id}
                    className={`glass relative flex flex-col justify-between rounded-2xl p-4 transition-all duration-200 ${
                      isCancelled ? "opacity-50" : "hover:border-accent/40"
                    }`}
                  >
                    <div>
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-1.5">
                          <span className="rounded-md bg-accent/10 px-2 py-0.5 font-mono text-[10px] font-medium text-accent">
                            {formatDateHeader(m.start_time)}
                          </span>
                          {m.team && <TeamBadge team={m.team} />}
                        </div>

                        {!isCancelled && (
                          <button
                            type="button"
                            onClick={() => handleCancelMeeting(m.id)}
                            className="rounded-lg p-1 text-muted transition hover:bg-danger/10 hover:text-danger"
                            title="Cancel meeting"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>

                      <h4 className="mt-2.5 font-semibold text-sm text-text leading-snug">{m.title}</h4>
                      {m.description && <p className="mt-1 text-xs text-muted line-clamp-2">{m.description}</p>}

                      <div className="mt-3 flex items-center gap-2 text-xs text-text-2">
                        <Clock size={13} className="text-muted" />
                        <span className="font-mono text-[11px]">
                          {formatTime(m.start_time)} - {formatTime(m.end_time)}
                        </span>
                      </div>

                      <div className="mt-1.5 flex items-center gap-2 text-xs text-text-2">
                        <Video size={13} className="text-muted" />
                        <span className="truncate text-xs text-muted">{m.location_or_link || "Google Meet"}</span>
                      </div>
                    </div>

                    {/* Attendees footer */}
                    <div className="mt-4 flex items-center justify-between border-t border-line/20 pt-3">
                      <div className="flex items-center gap-1">
                        <div className="flex -space-x-1.5">
                          {m.attendees?.slice(0, 4).map((att, i) => (
                            <span
                              key={i}
                              title={typeof att === "object" ? att.name : att}
                              className="inline-block h-6 w-6 rounded-full ring-2 ring-background"
                            >
                              <Avatar name={typeof att === "object" ? att.name : String(att)} size={24} />
                            </span>
                          ))}
                        </div>
                        {m.attendees?.length > 4 && (
                          <span className="font-mono text-[10px] text-muted">
                            +{m.attendees.length - 4}
                          </span>
                        )}
                      </div>

                      {m.host_name && (
                        <span className="text-[11px] text-muted">
                          Host: <span className="text-text-2 font-medium">{m.host_name}</span>
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Schedule Meeting Modal */}
      {showModal && (
        <ScheduleMeetingModal
          defaultDate={selectedDateForNew || todayIso}
          customers={customers}
          onClose={() => setShowModal(false)}
          onSuccess={() => {
            setShowModal(false);
            fetchMeetings();
          }}
        />
      )}

      {/* Check Free Slots Modal */}
      {showSlotFinder && (
        <SlotFinderModal
          customers={customers}
          onClose={() => setShowSlotFinder(false)}
          onSelectSlot={(date, timeStr) => {
            setShowSlotFinder(false);
            setSelectedDateForNew(date);
            setShowModal(true);
          }}
        />
      )}

      {/* Day Detail Modal - everything scheduled on the clicked day */}
      {selectedDayDetail && (
        <DayDetailModal
          date={selectedDayDetail}
          meetings={(meetingsByDate[selectedDayDetail] || []).slice().sort((a, b) =>
            a.start_time.localeCompare(b.start_time)
          )}
          onClose={() => setSelectedDayDetail(null)}
          onCancelMeeting={handleCancelMeeting}
          onScheduleNew={(iso) => {
            setSelectedDayDetail(null);
            setSelectedDateForNew(iso);
            setShowModal(true);
          }}
        />
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Day Detail Modal - everything scheduled on one calendar day
// --------------------------------------------------------------------------- //
function DayDetailModal({ date, meetings, onClose, onCancelMeeting, onScheduleNew }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="glass max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-line/30 p-6 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-line/20">
          <div className="flex items-center gap-2">
            <CalendarIcon size={18} className="text-accent" />
            <div>
              <h3 className="font-semibold text-text">{formatDateHeader(date)}</h3>
              <p className="text-[11px] text-muted">
                {meetings.length} meeting{meetings.length === 1 ? "" : "s"} scheduled
              </p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-muted hover:bg-glass hover:text-text">
            <X size={16} />
          </button>
        </div>

        <div className="mt-4 space-y-3">
          {meetings.length === 0 ? (
            <div className="rounded-xl border border-dashed border-line/30 p-8 text-center text-muted">
              <CalendarIcon size={26} className="mx-auto mb-2 opacity-40" />
              <p className="text-xs">Nothing scheduled on this day.</p>
            </div>
          ) : (
            meetings.map((m) => {
              const isCancelled = m.status === "cancelled";
              return (
                <div
                  key={m.id}
                  className={`rounded-xl border border-line/25 bg-glass/40 p-3.5 ${isCancelled ? "opacity-50" : ""}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <Clock size={12} className="text-muted" />
                        <span className="font-mono text-[11px] text-text-2">
                          {formatTime(m.start_time)} - {formatTime(m.end_time)}
                        </span>
                        {m.team && <TeamBadge team={m.team} />}
                        {isCancelled && (
                          <span className="rounded-full bg-danger/10 px-2 py-0.5 text-[9px] font-medium uppercase text-danger">
                            Cancelled
                          </span>
                        )}
                      </div>
                      <h4 className="mt-1.5 font-semibold text-sm text-text leading-snug">{m.title}</h4>
                      {m.description && <p className="mt-1 text-xs text-muted">{m.description}</p>}
                    </div>

                    {!isCancelled && (
                      <button
                        type="button"
                        onClick={() => onCancelMeeting(m.id)}
                        className="shrink-0 rounded-lg p-1 text-muted transition hover:bg-danger/10 hover:text-danger"
                        title="Cancel meeting"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>

                  <div className="mt-2.5 flex items-center gap-2 text-xs text-text-2">
                    <Video size={13} className="text-muted" />
                    <span className="truncate text-xs text-muted">{m.location_or_link || "Google Meet"}</span>
                  </div>

                  {m.host_name && (
                    <div className="mt-1.5 text-[11px] text-muted">
                      Host: <span className="text-text-2 font-medium">{m.host_name}</span>
                    </div>
                  )}

                  {m.attendees?.length > 0 && (
                    <div className="mt-2 flex items-center gap-1.5">
                      <Users size={12} className="text-muted" />
                      <div className="flex flex-wrap items-center gap-1">
                        {m.attendees.map((att, i) => (
                          <span
                            key={i}
                            className="rounded-full border border-line/25 bg-background/40 px-1.5 py-0.5 text-[10px] text-text-2"
                          >
                            {typeof att === "object" ? att.name : att}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="mt-4 border-t border-line/20 pt-3">
          <button
            type="button"
            onClick={() => onScheduleNew(date)}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-line/30 bg-glass/30 px-3.5 py-2 text-xs font-medium text-text-2 transition hover:bg-accent hover:text-white"
          >
            <Plus size={14} />
            Schedule a meeting on this day
          </button>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Schedule Meeting Modal
// --------------------------------------------------------------------------- //
function ScheduleMeetingModal({ defaultDate, customers, onClose, onSuccess }) {
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(defaultDate);
  const [timeStr, setTimeStr] = useState("10:00");
  const [duration, setDuration] = useState(30);
  const [team, setTeam] = useState("Development");
  const [hostId, setHostId] = useState("");
  const [selectedAttendees, setSelectedAttendees] = useState([]);
  const [location, setLocation] = useState("Google Meet");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const toggleAttendee = (person) => {
    if (selectedAttendees.some((a) => a.id === person.id)) {
      setSelectedAttendees((prev) => prev.filter((a) => a.id !== person.id));
    } else {
      setSelectedAttendees((prev) => [...prev, person]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Please enter a meeting title.");
      return;
    }

    setSubmitting(true);
    setError(null);

    const startIso = `${date}T${timeStr}:00`;

    try {
      await api.createMeeting({
        title,
        start_time: startIso,
        duration_minutes: Number(duration),
        host_id: hostId ? Number(hostId) : null,
        attendees: selectedAttendees,
        team,
        location_or_link: location,
        description,
      });
      onSuccess();
    } catch (err) {
      setError(api.errorMessage(err, "Failed to schedule meeting."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="glass max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-line/30 p-6 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-line/20">
          <div className="flex items-center gap-2">
            <CalendarCheck size={18} className="text-accent" />
            <h3 className="font-semibold text-text">Schedule Team Meeting</h3>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-muted hover:bg-glass hover:text-text">
            <X size={16} />
          </button>
        </div>

        {error && (
          <div className="mt-3 flex items-center gap-2 rounded-xl bg-danger/10 p-3 text-xs text-danger">
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-4 space-y-3.5">
          <div>
            <label className="block font-mono text-[11px] uppercase text-muted">Title / Topic *</label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Sprint Backlog & Architecture Sync"
              className="mt-1 w-full rounded-xl border border-line/30 bg-background/50 p-2.5 text-xs text-text placeholder-muted focus:border-accent focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-3 gap-2.5">
            <div>
              <label className="block font-mono text-[11px] uppercase text-muted">Date</label>
              <input
                type="date"
                required
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="mt-1 w-full rounded-xl border border-line/30 bg-background/50 p-2 text-xs text-text focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-mono text-[11px] uppercase text-muted">Start Time</label>
              <input
                type="time"
                required
                value={timeStr}
                onChange={(e) => setTimeStr(e.target.value)}
                className="mt-1 w-full rounded-xl border border-line/30 bg-background/50 p-2 text-xs text-text focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-mono text-[11px] uppercase text-muted">Duration</label>
              <select
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                className="mt-1 w-full rounded-xl border border-line/30 bg-background/50 p-2 text-xs text-text focus:border-accent focus:outline-none"
              >
                <option value={15}>15 mins</option>
                <option value={30}>30 mins</option>
                <option value={45}>45 mins</option>
                <option value={60}>1 hour</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="block font-mono text-[11px] uppercase text-muted">Team</label>
              <select
                value={team}
                onChange={(e) => setTeam(e.target.value)}
                className="mt-1 w-full rounded-xl border border-line/30 bg-background/50 p-2 text-xs text-text focus:border-accent focus:outline-none"
              >
                {TEAMS.filter((t) => t !== "All").map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-mono text-[11px] uppercase text-muted">Organizer / Host</label>
              <select
                value={hostId}
                onChange={(e) => setHostId(e.target.value)}
                className="mt-1 w-full rounded-xl border border-line/30 bg-background/50 p-2 text-xs text-text focus:border-accent focus:outline-none"
              >
                <option value="">Select host...</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.team})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block font-mono text-[11px] uppercase text-muted mb-1">
              Select Attendees ({selectedAttendees.length} chosen)
            </label>
            <div className="scrollbar-thin max-h-32 overflow-y-auto rounded-xl border border-line/25 bg-background/30 p-2">
              <div className="flex flex-wrap gap-1.5">
                {customers.map((c) => {
                  const isSelected = selectedAttendees.some((a) => a.id === c.id);
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => toggleAttendee(c)}
                      className={`flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] transition ${
                        isSelected
                          ? "bg-accent text-white"
                          : "border border-line/20 bg-glass/40 text-text-2 hover:bg-glass/80"
                      }`}
                    >
                      <Avatar name={c.name} size={16} />
                      <span>{c.name}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div>
            <label className="block font-mono text-[11px] uppercase text-muted">Location / Link</label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Google Meet or Room Alpha"
              className="mt-1 w-full rounded-xl border border-line/30 bg-background/50 p-2 text-xs text-text focus:border-accent focus:outline-none"
            />
          </div>

          <div>
            <label className="block font-mono text-[11px] uppercase text-muted">Agenda Description</label>
            <textarea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Topics to discuss, deliverables..."
              className="mt-1 w-full rounded-xl border border-line/30 bg-background/50 p-2 text-xs text-text focus:border-accent focus:outline-none"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-line/20">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-line/30 px-4 py-2 text-xs text-muted hover:bg-glass hover:text-text"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-xl bg-accent px-4 py-2 text-xs font-medium text-white shadow-lg shadow-accent/25 hover:bg-accent/90 disabled:opacity-50"
            >
              {submitting ? "Scheduling..." : "Confirm & Schedule"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Free Slots Finder Modal
// --------------------------------------------------------------------------- //
function SlotFinderModal({ customers, onClose, onSelectSlot }) {
  const [selectedPeople, setSelectedPeople] = useState([]);
  const [targetDate, setTargetDate] = useState(toLocalIsoDate(new Date()));
  const [duration, setDuration] = useState(30);
  const [slotsData, setSlotsData] = useState(null);
  const [checking, setChecking] = useState(false);

  const handleCheck = async () => {
    if (selectedPeople.length === 0) return;
    setChecking(true);
    try {
      const attendeesQuery = selectedPeople.map((p) => p.name).join(",");
      const { data } = await api.getFreeSlots({
        attendees: attendeesQuery,
        date: targetDate,
        duration_minutes: duration,
      });
      setSlotsData(data.data);
    } catch (err) {
      alert(api.errorMessage(err, "Failed to compute free slots."));
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="glass max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-line/30 p-6 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-line/20">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-accent" />
            <h3 className="font-semibold text-text">Intelligent Slot & Conflict Finder</h3>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-muted hover:bg-glass hover:text-text">
            <X size={16} />
          </button>
        </div>

        <p className="mt-2 text-xs text-muted">
          Cross-references leaves, existing meetings, and work hours to discover conflict-free times.
        </p>

        <div className="mt-4 space-y-3">
          <div>
            <label className="block font-mono text-[11px] uppercase text-muted mb-1">
              Select Participants ({selectedPeople.length} selected)
            </label>
            <div className="scrollbar-thin max-h-28 overflow-y-auto rounded-xl border border-line/25 bg-background/30 p-2">
              <div className="flex flex-wrap gap-1.5">
                {customers.map((c) => {
                  const isSelected = selectedPeople.some((p) => p.id === c.id);
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => {
                        if (isSelected) setSelectedPeople((prev) => prev.filter((p) => p.id !== c.id));
                        else setSelectedPeople((prev) => [...prev, c]);
                      }}
                      className={`flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] transition ${
                        isSelected
                          ? "bg-accent text-white"
                          : "border border-line/20 bg-glass/40 text-text-2 hover:bg-glass/80"
                      }`}
                    >
                      <Avatar name={c.name} size={15} />
                      <span>{c.name}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-mono text-[11px] uppercase text-muted">Target Date</label>
              <input
                type="date"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
                className="mt-1 w-full rounded-xl border border-line/30 bg-background/50 p-2 text-xs text-text focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <label className="block font-mono text-[11px] uppercase text-muted">Duration</label>
              <select
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                className="mt-1 w-full rounded-xl border border-line/30 bg-background/50 p-2 text-xs text-text focus:border-accent focus:outline-none"
              >
                <option value={15}>15 mins</option>
                <option value={30}>30 mins</option>
                <option value={45}>45 mins</option>
                <option value={60}>1 hour</option>
              </select>
            </div>
          </div>

          <button
            type="button"
            onClick={handleCheck}
            disabled={checking || selectedPeople.length === 0}
            className="w-full rounded-xl bg-accent/20 border border-accent/40 py-2.5 text-xs font-semibold text-accent transition hover:bg-accent hover:text-white disabled:opacity-50"
          >
            {checking ? "Analyzing schedules..." : "Find Available Slots"}
          </button>
        </div>

        {/* Results grid */}
        {slotsData && (
          <div className="mt-5 border-t border-line/20 pt-4">
            <div className="flex items-center justify-between text-xs mb-3">
              <span className="font-medium text-text">
                Results for {slotsData.date}:{" "}
                <span className="text-success font-semibold">{slotsData.available_slots_count} free</span> /{" "}
                {slotsData.total_slots} total
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 max-h-48 overflow-y-auto scrollbar-thin">
              {slotsData.slots?.map((slot, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => {
                    if (slot.available) {
                      const timeOnly = slot.start.split("T")[1]?.slice(0, 5) || "10:00";
                      onSelectSlot(slotsData.date, timeOnly);
                    }
                  }}
                  className={`rounded-xl border p-2.5 text-left transition ${
                    slot.available
                      ? "border-success/30 bg-success/10 hover:bg-success/20 cursor-pointer"
                      : "border-line/20 bg-background/20 opacity-40 cursor-not-allowed"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-medium text-text">{slot.time_label}</span>
                    {slot.available ? (
                      <CheckCircle2 size={13} className="text-success" />
                    ) : (
                      <AlertCircle size={13} className="text-danger" />
                    )}
                  </div>
                  {slot.conflicts?.length > 0 && (
                    <p className="mt-1 text-[9px] text-danger truncate">{slot.conflicts[0]}</p>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
