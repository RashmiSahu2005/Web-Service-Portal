import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import ApplicationCatalog from '../pages/ApplicationCatalog/ApplicationCatalog.jsx';
import InstallationStatus from '../pages/InstallationStatus/InstallationStatus.jsx';
import AdminDashboard from '../pages/AdminDashboard/AdminDashboard.jsx';
import Navbar from '../components/Navbar/Navbar.jsx';
import Sidebar from '../components/Sidebar/Sidebar.jsx';

function App() {
  return (
    <Router>
      <div className="flex h-screen overflow-hidden bg-background">
        <Sidebar />
        <div className="flex flex-col flex-1 overflow-hidden">
          <Navbar />
          <main className="flex-1 overflow-x-hidden overflow-y-auto bg-background p-6">
            <Routes>
              <Route path="/" element={<ApplicationCatalog />} />
              <Route path="/status/:id" element={<InstallationStatus />} />
              <Route path="/admin" element={<AdminDashboard />} />
            </Routes>
          </main>
        </div>
      </div>
    </Router>
  );
}

export default App;
