/**
 * Global Event Bus for cross-module communication
 *
 * Used for communication between isolated feature modules (e.g., TestManagement)
 * and the main App.tsx orchestration layer.
 */

export type ExecutionStartEvent = {
  type: 'execution:start'
  payload: {
    planId: string
    planName: string
  }
}

export type ExecutionPauseEvent = {
  type: 'execution:pause'
  payload: {
    planId: string
  }
}

export type ExecutionResumeEvent = {
  type: 'execution:resume'
  payload: {
    planId: string
  }
}

export type ExecutionStopEvent = {
  type: 'execution:stop'
  payload: {
    planId: string
  }
}

export type ExecutionCompleteEvent = {
  type: 'execution:complete'
  payload: {
    planId: string
  }
}

export type AppEvent =
  | ExecutionStartEvent
  | ExecutionPauseEvent
  | ExecutionResumeEvent
  | ExecutionStopEvent
  | ExecutionCompleteEvent

type EventCallback<T extends AppEvent = AppEvent> = (event: T) => void

class EventBus {
  private listeners: Map<string, Set<EventCallback>> = new Map()

  on<T extends AppEvent>(type: T['type'], callback: EventCallback<T>): () => void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set())
    }
    this.listeners.get(type)!.add(callback as EventCallback)

    // Return unsubscribe function
    return () => {
      this.listeners.get(type)?.delete(callback as EventCallback)
    }
  }

  emit<T extends AppEvent>(event: T): void {
    const callbacks = this.listeners.get(event.type)
    if (callbacks) {
      callbacks.forEach((callback) => callback(event))
    }
  }

  off<T extends AppEvent>(type: T['type'], callback: EventCallback<T>): void {
    this.listeners.get(type)?.delete(callback as EventCallback)
  }
}

// Singleton instance
export const appEventBus = new EventBus()
