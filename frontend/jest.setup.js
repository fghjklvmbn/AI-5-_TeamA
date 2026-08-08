/**
 * Jest 테스트 환경 설정
 */

// React Native Mocks
jest.mock('react-native/Libraries/Animated/AnimatedAPI', () => ({
  ...jest.requireActual('react-native/Libraries/Animated/AnimatedAPI'),
  useSharedElement: jest.fn(),
  withSpring: jest.fn(),
  withTiming: jest.fn(),
  Node: {},
}));

jest.mock('@react-native-async-storage/async-storage', () => require('./__mocks__/AsyncStorage.js'));

// Fetch Mock
global.fetch = jest.fn();

/**
 * 테스트 환경에서 useTheme mock 설정
 */
jest.mock('../src/theme.ts', () => ({
  useTheme: () => ({
    colors: {
      ink: '#211B2D',
      muted: '#756D80',
      primary: '#7654D8',
      primaryDark: '#5B37BF',
      primarySoft: '#F0EAFE',
      lilac: '#E4D8FF',
      surface: '#FFFFFF',
      background: '#FBFAFD',
      border: '#EAE5EF',
      danger: '#C43D58',
      success: '#347D64',
      input: '#FEFDFE',
      subtle: '#F5F2F7',
      dangerSoft: '#FFF7F8',
      overlay: 'rgba(31,24,40,0.36)',
    },
    darkMode: false,
  }),
}));

/**
 * Mock Alert (React Native)
 */
jest.mock('react-native/Libraries/Alert', () => ({
  Alert: {
    alert: jest.fn(),
  },
}));

/**
 * Console logging mock (테스트 시 간소화)
 */
const originalConsole = console;
global.console = {
  log: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
  info: jest.fn(),
  debug: jest.fn(),
};

afterEach(() => {
  // 각 테스트마다 Console mock 초기화
  global.console.log.mockClear();
  global.console.warn.mockClear();
  global.console.error.mockClear();
});
