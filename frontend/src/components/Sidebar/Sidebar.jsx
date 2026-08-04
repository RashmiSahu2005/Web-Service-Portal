import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutGrid, Activity, Settings, HelpCircle, FileText } from 'lucide-react';

const Sidebar = () => {
  const mainNavItems = [
    { name: 'Applications', path: '/', icon: LayoutGrid },
    { name: 'Installation Status', path: '/status', icon: Activity },
    { name: 'Admin', path: '/admin', icon: Settings },
  ];
  
  const resourceNavItems = [
    { name: 'Documentation', path: '#', icon: FileText },
    { name: 'Help Center', path: '#', icon: HelpCircle },
  ];

  return (
    <aside className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col transition-all duration-300">
      <div className="h-20 flex flex-col justify-center px-6 border-b border-gray-200">
        <div className="flex items-center text-gray-900">
          <LayoutGrid className="w-6 h-6 text-[#004aad] mr-2" />
          <span className="text-xl font-bold">Corporate Portal</span>
        </div>
        <span className="text-xs text-gray-500 mt-1 pl-8">Management Suite</span>
      </div>
      
      <div className="flex-1 py-6 px-4 space-y-8 overflow-y-auto">
        <div>
           <p className="px-4 text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Main Menu</p>
           <nav className="space-y-1">
             {mainNavItems.map((item) => (
               <NavLink
                 key={item.name}
                 to={item.path}
                 className={({ isActive }) => 
                   `flex items-center px-4 py-2.5 rounded-lg transition-all duration-200 group text-sm font-medium ${
                     isActive 
                       ? "bg-gray-200 text-gray-900" 
                       : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                   }`
                 }
               >
                 <item.icon className={`w-5 h-5 mr-3 transition-transform ${window.location.pathname === item.path ? 'text-gray-700' : 'text-gray-500'}`} />
                 {item.name}
               </NavLink>
             ))}
           </nav>
        </div>
        
        <div>
           <p className="px-4 text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Resources</p>
           <nav className="space-y-1">
             {resourceNavItems.map((item) => (
               <a
                 key={item.name}
                 href={item.path}
                 className="flex items-center px-4 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900 rounded-lg transition-all duration-200 group"
               >
                 <item.icon className="w-5 h-5 mr-3 text-gray-500" />
                 {item.name}
               </a>
             ))}
           </nav>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
