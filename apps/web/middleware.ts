import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// ВРЕМЕННАЯ заглушка до задачи #3 (Auth.js, «команда = арендатор»).
// Включается ТОЛЬКО если заданы обе переменные BASIC_AUTH_USER / BASIC_AUTH_PASSWORD.
// Локальная разработка их не задаёт — сайт открыт. Захардкоженной пары admin/admin
// больше нет: она закрывала сайт паролем, известным любому, кто видел репозиторий.
const USER = process.env.BASIC_AUTH_USER
const PASSWORD = process.env.BASIC_AUTH_PASSWORD
const ENABLED = Boolean(USER && PASSWORD)

function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i)
  return diff === 0
}

export function middleware(req: NextRequest) {
  if (!ENABLED) return NextResponse.next()

  const header = req.headers.get('authorization')

  if (header?.startsWith('Basic ')) {
    try {
      const [user, ...rest] = atob(header.slice(6)).split(':')
      const password = rest.join(':')
      if (safeEqual(user, USER as string) && safeEqual(password, PASSWORD as string)) {
        return NextResponse.next()
      }
    } catch {
      // повреждённый base64 — падаем в 401 ниже
    }
  }

  return new NextResponse('Auth required', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="AGORA"' },
  })
}

export const config = {
  matcher: '/((?!api|_next/static|_next/image|favicon.ico).*)',
}
