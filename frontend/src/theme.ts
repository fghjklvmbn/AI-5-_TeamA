import React, { createContext, useContext } from 'react';

export type ThemeColors = {
  ink: string;
  muted: string;
  primary: string;
  primaryDark: string;
  primarySoft: string;
  lilac: string;
  surface: string;
  background: string;
  border: string;
  danger: string;
  success: string;
  input: string;
  subtle: string;
  dangerSoft: string;
  overlay: string;
};

export const lightColors: ThemeColors = {
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
};

export const darkColors: ThemeColors = {
  ink: '#F4EFFA',
  muted: '#B9AFC4',
  primary: '#9B7BEA',
  primaryDark: '#C6B2FA',
  primarySoft: '#342752',
  lilac: '#554276',
  surface: '#211B29',
  background: '#17131D',
  border: '#3D3447',
  danger: '#FF879C',
  success: '#70C6A6',
  input: '#2A2332',
  subtle: '#2D2635',
  dangerSoft: '#38242C',
  overlay: 'rgba(5,3,8,0.72)',
};

// Kept for non-visual modules and gradual compatibility.
export const colors = lightColors;

type ThemeValue = { darkMode: boolean; colors: ThemeColors };
const ThemeContext = createContext<ThemeValue>({ darkMode: false, colors: lightColors });

export function ThemeProvider({ darkMode, children }: { darkMode: boolean; children: React.ReactNode }) {
  return React.createElement(
    ThemeContext.Provider,
    { value: { darkMode, colors: darkMode ? darkColors : lightColors } },
    children,
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}

export const shadow = {
  shadowColor: '#4B346B',
  shadowOffset: { width: 0, height: 8 },
  shadowOpacity: 0.12,
  shadowRadius: 20,
  elevation: 5,
};
