export interface Transport {
  connect(endpoint: string, options?: Record<string, unknown>): Promise<void>
  disconnect(): Promise<void>
  send(command: string, payload?: unknown): Promise<unknown>
}

export class MockTransport implements Transport {
  private connected = false

  async connect(endpoint: string): Promise<void> {
    if (!endpoint) throw new Error('missing endpoint')
    await new Promise((resolve) => setTimeout(resolve, 50))
    this.connected = true
  }

  async disconnect(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, 20))
    this.connected = false
  }

  async send(command: string, payload?: unknown): Promise<unknown> {
    if (!this.connected) {
      throw new Error('transport not connected')
    }
    if (command === 'status') {
      return {
        state: 'running',
        operatingScenario: 'mock-scenario',
        temperatureC: 29.5,
        warnings: [],
      }
    }
    if (command === 'uploadAsset') {
      const name = (payload as { name?: string })?.name ?? 'unknown'
      return { assetId: `mock-${name}` }
    }
    return { acknowledgedCommand: command, receivedPayload: payload }
  }
}
