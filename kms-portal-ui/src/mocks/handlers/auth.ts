/**
 * Auth Mock API Handlers
 *
 * MSW handlers for authentication endpoints
 */

import { http, HttpResponse, delay } from 'msw';

// Mock users database
const MOCK_USERS = [
  {
    id: 'user-001',
    userId: 'admin',
    password: 'admin123',
    email: 'admin@kms.local',
    name: 'Admin User',
    role: 'admin',
    department: 'IT',
    avatar: null,
  },
  {
    id: 'user-002',
    userId: 'user',
    password: 'user123',
    email: 'user@kms.local',
    name: 'Test User',
    role: 'user',
    department: 'Engineering',
    avatar: null,
  },
  {
    id: 'user-003',
    userId: 'demo',
    password: 'demo123',
    email: 'demo@kms.local',
    name: 'Demo User',
    role: 'viewer',
    department: 'Sales',
    avatar: null,
  },
];

// Session storage for mock tokens
const activeSessions = new Map<string, { userId: string; expiresAt: number }>();

// Generate mock JWT token
function generateToken(userId: string): string {
  const token = `mock-jwt-${userId}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  activeSessions.set(token, {
    userId,
    expiresAt: Date.now() + 24 * 60 * 60 * 1000, // 24 hours
  });
  return token;
}

// Validate token
function validateToken(authHeader: string | null): string | null {
  if (!authHeader) return null;
  const token = authHeader.replace('Bearer ', '');
  const session = activeSessions.get(token);
  if (!session || session.expiresAt < Date.now()) {
    activeSessions.delete(token);
    return null;
  }
  return session.userId;
}

export const authHandlers = [
  // Login
  http.post('/api/v1/auth/login', async ({ request }) => {
    await delay(500); // Simulate network delay

    const body = (await request.json()) as { userId?: string; username?: string; password: string };
    const userId = body.userId || body.username; // Support both userId and username
    const { password } = body;

    const user = MOCK_USERS.find((u) => u.userId === userId && u.password === password);

    if (!user) {
      return HttpResponse.json(
        { error: 'Invalid credentials', code: 'AUTH_INVALID_CREDENTIALS' },
        { status: 401 }
      );
    }

    const accessToken = generateToken(user.id);
    const refreshToken = generateToken(`refresh-${user.id}`);

    return HttpResponse.json({
      accessToken,
      refreshToken,
      expiresIn: 86400,
      user: {
        id: user.id,
        userId: user.userId,
        email: user.email,
        name: user.name,
        role: user.role,
        department: user.department,
        avatar: user.avatar,
      },
    });
  }),

  // Get current user
  http.get('/api/v1/auth/me', async ({ request }) => {
    await delay(200);

    const authHeader = request.headers.get('Authorization');
    const userId = validateToken(authHeader);

    if (!userId) {
      return HttpResponse.json(
        { error: 'Unauthorized', code: 'AUTH_UNAUTHORIZED' },
        { status: 401 }
      );
    }

    const user = MOCK_USERS.find((u) => u.id === userId);
    if (!user) {
      return HttpResponse.json({ error: 'User not found', code: 'USER_NOT_FOUND' }, { status: 404 });
    }

    return HttpResponse.json({
      id: user.id,
      userId: user.userId,
      email: user.email,
      name: user.name,
      role: user.role,
      department: user.department,
      avatar: user.avatar,
    });
  }),

  // Refresh token
  http.post('/api/v1/auth/refresh', async ({ request }) => {
    await delay(200);

    const body = (await request.json()) as { refreshToken: string };
    const session = activeSessions.get(body.refreshToken);

    if (!session || session.expiresAt < Date.now()) {
      return HttpResponse.json(
        { error: 'Invalid refresh token', code: 'AUTH_INVALID_REFRESH_TOKEN' },
        { status: 401 }
      );
    }

    const userId = session.userId.replace('refresh-', '');
    const newAccessToken = generateToken(userId);

    return HttpResponse.json({
      accessToken: newAccessToken,
      expiresIn: 86400,
    });
  }),

  // Logout
  http.post('/api/v1/auth/logout', async ({ request }) => {
    await delay(100);

    const authHeader = request.headers.get('Authorization');
    if (authHeader) {
      const token = authHeader.replace('Bearer ', '');
      activeSessions.delete(token);
    }

    return HttpResponse.json({ success: true });
  }),

  // Google OAuth (mock)
  http.post('/api/v1/auth/google', async () => {
    await delay(500);

    // Simulate Google OAuth - return demo user
    const user = MOCK_USERS[2]; // Demo user
    const accessToken = generateToken(user.id);
    const refreshToken = generateToken(`refresh-${user.id}`);

    return HttpResponse.json({
      accessToken,
      refreshToken,
      expiresIn: 86400,
      user: {
        id: user.id,
        userId: user.userId,
        email: user.email,
        name: user.name,
        role: user.role,
        department: user.department,
        avatar: user.avatar,
      },
    });
  }),
];
