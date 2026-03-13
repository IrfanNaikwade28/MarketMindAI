import { NavLink, Outlet } from 'react-router-dom'

const NAV = [
  { to: '/dashboard',   label: 'Dashboard',   icon: '▦' },
  { to: '/campaigns/new', label: 'New Campaign', icon: '+' },
  { to: '/trends',      label: 'Trend Reports', icon: '↗' },
  { to: '/brand-health',label: 'Brand Health',  icon: '♥' },
  { to: '/engagement',  label: 'Engagement',    icon: '◎' },
  { to: '/mentor',      label: 'Mentor Portal', icon: '✦' },
]

export default function MainLayout() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 flex flex-col bg-gray-900 border-r border-gray-800">
        {/* Logo */}
        <div className="px-5 py-4 border-b border-gray-800">
          <span className="text-brand-400 font-bold tracking-tight text-sm">AI COUNCIL</span>
          <p className="text-gray-500 text-xs mt-0.5">Multi-Agent Strategy</p>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 space-y-0.5 px-2 overflow-y-auto">
          {NAV.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-brand-600/20 text-brand-300 font-medium'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                }`
              }
            >
              <span className="w-4 text-center opacity-70">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-800">
          <p className="text-gray-600 text-xs">Powered by Groq · LLaMA 4</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto bg-gray-950">
        <Outlet />
      </main>
    </div>
  )
}
