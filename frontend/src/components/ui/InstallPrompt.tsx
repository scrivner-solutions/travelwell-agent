import { useEffect, useState } from 'react'
import { Share, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'

/**
 * Chrome fires beforeinstallprompt on an installable page and lets the page
 * defer the browser's own mini-infobar to a button of its choosing. iOS has no
 * equivalent event and no install API at all, so there the only honest thing to
 * do is explain the Share-sheet gesture.
 */
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const DISMISSED_KEY = 'twl.install-dismissed'

function isInstalled(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    window.matchMedia('(display-mode: minimal-ui)').matches ||
    // iOS carried this flag for years before it honoured the display-mode query.
    (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  )
}

function isIos(): boolean {
  const ua = window.navigator.userAgent
  // iPadOS 13+ reports a Mac user agent; touch points are what separate the two.
  return (
    /iphone|ipad|ipod/i.test(ua) ||
    (/macintosh/i.test(ua) && window.navigator.maxTouchPoints > 1)
  )
}

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(DISMISSED_KEY) === '1'
  } catch {
    // Private mode and blocked site data both throw on access; showing the
    // banner is the harmless direction to fail.
    return false
  }
}

/**
 * Renders nothing unless the app is installable and not already installed, so
 * it is safe to mount on any screen.
 */
export function InstallPrompt({ className = '' }: { className?: string }) {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)
  const [dismissed, setDismissed] = useState(readDismissed)
  const [installed, setInstalled] = useState(isInstalled)

  useEffect(() => {
    const onBeforeInstall = (event: Event) => {
      // Without preventDefault Chrome shows its own mini-infobar and the event
      // is spent; holding it is what lets our button drive the real dialog.
      event.preventDefault()
      setDeferred(event as BeforeInstallPromptEvent)
    }
    const onInstalled = () => setInstalled(true)
    window.addEventListener('beforeinstallprompt', onBeforeInstall)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  const dismiss = () => {
    setDismissed(true)
    try {
      window.localStorage.setItem(DISMISSED_KEY, '1')
    } catch {
      // Nothing to persist to; the banner stays gone for this session only.
    }
  }

  const install = async () => {
    if (!deferred) return
    await deferred.prompt()
    // The event is single use whatever the user chose. appinstalled handles the
    // accepted case; clearing here retires the button on a decline.
    setDeferred(null)
  }

  const ios = isIos()
  if (installed || dismissed || (!ios && !deferred)) return null

  return (
    <section
      aria-label="Install TravelWell"
      className={`rounded-card border border-border bg-card px-4 py-3 ${className}`}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <p className="text-body-sm font-semibold text-ink">Add to your home screen</p>
          <p className="mt-0.5 text-body-sm text-muted">
            {ios ? (
              <>
                Tap{' '}
                <Share
                  size={15}
                  className="inline-block align-[-2px]"
                  aria-hidden
                />{' '}
                Share, then Add to Home Screen. It opens without the browser bar.
              </>
            ) : (
              'Opens full screen, without the browser bar.'
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss"
          className="-mr-1 -mt-1 shrink-0 rounded-control p-2 text-muted-soft hover:text-ink focus-visible:outline-2 focus-visible:outline-primary"
        >
          <X size={15} aria-hidden />
        </button>
      </div>
      {/* Full width under the copy: beside it the heading wraps and the button
          crowds the text on a narrow phone. */}
      {!ios && (
        <Button onClick={() => void install()} className="mt-3 h-10 w-full">
          Install
        </Button>
      )}
    </section>
  )
}
