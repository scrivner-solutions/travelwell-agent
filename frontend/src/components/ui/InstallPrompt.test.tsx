import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { act } from 'react'
import { InstallPrompt } from './InstallPrompt'

const DESKTOP_UA = 'Mozilla/5.0 (X11; Linux x86_64) Chrome/120'
const IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/605'

function setPlatform(userAgent: string, maxTouchPoints = 0) {
  Object.defineProperty(window.navigator, 'userAgent', {
    value: userAgent,
    configurable: true,
  })
  Object.defineProperty(window.navigator, 'maxTouchPoints', {
    value: maxTouchPoints,
    configurable: true,
  })
}

// Node 25 ships Web Storage globals that shadow jsdom's and lack most of the
// Storage methods, so tests touching localStorage have to supply their own.
function installLocalStorage() {
  const store = new Map<string, string>()
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, String(value)),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
      key: (index: number) => [...store.keys()][index] ?? null,
      get length() {
        return store.size
      },
    },
  })
}

// jsdom has no layout engine, so every media query has to be answered by hand.
function setDisplayMode(standalone: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: standalone && query.includes('standalone'),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia
}

function fireBeforeInstallPrompt() {
  const event = new Event('beforeinstallprompt') as Event & {
    prompt: () => Promise<void>
    userChoice: Promise<{ outcome: string }>
  }
  event.prompt = vi.fn().mockResolvedValue(undefined)
  event.userChoice = Promise.resolve({ outcome: 'accepted' })
  act(() => {
    window.dispatchEvent(event)
  })
  return event
}

describe('InstallPrompt', () => {
  beforeEach(() => {
    installLocalStorage()
    setPlatform(DESKTOP_UA)
    setDisplayMode(false)
  })

  it('stays hidden until the browser says the app is installable', () => {
    render(<InstallPrompt />)
    expect(screen.queryByRole('region', { name: 'Install TravelWell' })).toBeNull()
  })

  it('offers a real install button once beforeinstallprompt fires', async () => {
    render(<InstallPrompt />)
    const event = fireBeforeInstallPrompt()

    const button = await screen.findByRole('button', { name: 'Install' })
    await userEvent.click(button)
    expect(event.prompt).toHaveBeenCalledOnce()
  })

  it('explains the Share gesture on iOS, where no install API exists', () => {
    setPlatform(IPHONE_UA)
    render(<InstallPrompt />)

    expect(screen.getByText(/Add to Home Screen/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Install' })).toBeNull()
  })

  it('treats an iPad reporting a Mac user agent as iOS', () => {
    setPlatform('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Safari/605', 5)
    render(<InstallPrompt />)
    expect(screen.getByText(/Add to Home Screen/)).toBeInTheDocument()
  })

  it('says nothing once the app is already installed', () => {
    setPlatform(IPHONE_UA)
    setDisplayMode(true)
    render(<InstallPrompt />)
    expect(screen.queryByRole('region', { name: 'Install TravelWell' })).toBeNull()
  })

  it('stays dismissed across reloads', async () => {
    setPlatform(IPHONE_UA)
    const { unmount } = render(<InstallPrompt />)
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByRole('region', { name: 'Install TravelWell' })).toBeNull()

    unmount()
    render(<InstallPrompt />)
    expect(screen.queryByRole('region', { name: 'Install TravelWell' })).toBeNull()
  })
})
