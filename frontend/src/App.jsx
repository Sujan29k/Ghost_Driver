/**
 * App.jsx — Root component assembling the Ghost Driver operator dashboard.
 */
import React from 'react';
import Header from './components/layout/Header';
import StatusBar from './components/layout/StatusBar';
import VideoFeed from './components/video/VideoFeed';
import TelemetryPanel from './components/telemetry/TelemetryPanel';
import ControlStatus from './components/controls/ControlStatus';
import KeyboardHelp from './components/controls/KeyboardHelp';
import ConnectionControls from './components/connection/ConnectionControls';

// Global hooks (top-level, run once)
import useTelemetry from './hooks/useTelemetry';
import useKeyboard from './hooks/useKeyboard';

export default function App() {
  // Activate global hooks
  useTelemetry();
  useKeyboard();

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-ghost-bg">
      {/* Top Header */}
      <Header />

      {/* Main Content */}
      <div className="flex flex-1 overflow-hidden gap-3 p-3">

        {/* LEFT SIDEBAR — Connection + Controls */}
        <aside className="flex flex-col gap-3 w-56 flex-shrink-0">
          <ConnectionControls />
          <ControlStatus />
          <KeyboardHelp />
          {/* Ghost gradient bottom fill */}
          <div className="flex-1 ghost-panel opacity-30 grid-bg" />
        </aside>

        {/* CENTER — Video Feed */}
        <main className="flex-1 flex flex-col min-w-0">
          <VideoFeed />
        </main>

        {/* RIGHT SIDEBAR — Telemetry */}
        <aside className="flex-shrink-0">
          <TelemetryPanel />
        </aside>

      </div>

      {/* Bottom Status Bar */}
      <StatusBar />
    </div>
  );
}
