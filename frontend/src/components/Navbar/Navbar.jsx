import React from 'react';
import { Bell, User, Search } from 'lucide-react';

const Navbar = () => {
  return (
    <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200">
      <div className="flex items-center flex-1">
        <div className="relative w-96 hidden md:block">
          <span className="absolute inset-y-0 left-0 flex items-center pl-3">
            <Search className="w-5 h-5 text-gray-400" />
          </span>
          <input 
            type="text" 
            className="w-full py-2 pl-10 pr-4 text-gray-900 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-[#004aad] focus:ring-1 focus:ring-[#004aad] transition-colors placeholder-gray-400" 
            placeholder="Search resources, apps..." 
          />
        </div>
      </div>
      <div className="flex items-center space-x-4">
        <button className="p-2 text-gray-400 hover:text-gray-600 transition-colors">
          <Bell className="w-5 h-5" />
        </button>
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-full bg-[#004aad] flex items-center justify-center">
            <User className="w-5 h-5 text-white" />
          </div>
          <span className="text-sm font-medium text-gray-700 hidden md:block">Admin User</span>
        </div>
      </div>
    </header>
  );
};

export default Navbar;
