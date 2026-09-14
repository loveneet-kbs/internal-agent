import {
  LayoutDashboard,
  ListChecks,
  Users,
  Activity,
  Settings,
  Mail,
  Send,
  Network,
  CalendarClock,
  CalendarCheck,
  ClipboardList,
  Calendar
} from "lucide-react";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "work", label: "Tasks", icon: ClipboardList },
  { id: "customers", label: "Employees", icon: Users },
  { id: "meetings", label: "Meetings", icon: Calendar },
  { id: "teams", label: "Teams", icon: Network },
  { id: "attendance", label: "Attendance", icon: CalendarCheck },
  { id: "leave", label: "Leave", icon: CalendarClock },
  { id: "mail", label: "Mail Studio", icon: Mail },
  { id: "sent-mail", label: "Sent Mail", icon: Send },
  { id: "tasks", label: "Agent Runs", icon: ListChecks },
  { id: "activity", label: "API Activity", icon: Activity },
  { id: "settings", label: "Settings", icon: Settings }
];

export default function Sidebar({ active, onChange }) {
  return (
    <>
      {/* Desktop rail */}
      <aside className="hidden w-56 flex-shrink-0 p-3 md:block">
        <nav className="glass sticky top-20 space-y-1 rounded-2xl p-2">
          {NAV.map((item) => {
            const Icon = item.icon;
            const isActive = active === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onChange(item.id)}
                aria-current={isActive ? "page" : undefined}
                className={`group relative flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? "bg-accent/12 text-accent"
                    : "text-text-2 hover:bg-glass/40 hover:text-text"
                }`}
              >
                {/* Active marker, so state does not rely on colour alone */}
                <span
                  className={`absolute left-0 h-5 w-[3px] rounded-r-full bg-accent transition-all duration-200 ${
                    isActive ? "opacity-100" : "opacity-0"
                  }`}
                />
                <Icon
                  size={16}
                  className={`transition-transform duration-200 ${
                    isActive ? "scale-110" : "group-hover:scale-110"
                  }`}
                />
                {item.label}
              </button>
            );
          })}
        </nav>
      </aside>

      {/* Mobile bar */}
      <nav className="glass fixed inset-x-0 bottom-0 z-40 flex justify-around rounded-none border-x-0 border-b-0 px-1 py-1.5 md:hidden">
        {NAV.map((item) => {
          const Icon = item.icon;
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onChange(item.id)}
              aria-label={item.label}
              aria-current={isActive ? "page" : undefined}
              className={`flex flex-1 flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 transition-colors ${
                isActive ? "text-accent" : "text-muted"
              }`}
            >
              <Icon size={17} />
              <span className="text-[9px] font-medium leading-none">{item.label.split(" ")[0]}</span>
            </button>
          );
        })}
      </nav>
    </>
  );
}
