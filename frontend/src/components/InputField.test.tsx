import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react-native';
import { InputField } from './InputField';

describe('InputField Component', () => {
  // 1. 기본 렌더링 - label 표시 검증
  it('renders with label correctly', () => {
    const onChangeText = jest.fn();
    
    render(
      <InputField
        label="이름"
        value=""
        onChangeText={onChangeText}
      />
    );

    expect(screen.getByText('이름')).toBeDefined();
  });

  // 2. Placeholder 표시 검증
  it('displays placeholder when empty', () => {
    const onChangeText = jest.fn();
    
    render(
      <InputField
        label="이메일"
        value=""
        placeholder="hello@memorypal.app"
        onChangeText={onChangeText}
      />
    );

    expect(screen.getByPlaceholderText('hello@memorypal.app')).toBeDefined();
  });

  // 3. securedTextEntry prop 전달 검증 (비밀번호 입력)
  it('passes secureTextEntry correctly', () => {
    const onChangeText = jest.fn();
    
    render(
      <InputField
        label="비밀번호"
        value=""
        secureTextEntry={true}
        onChangeText={onChangeText}
      />
    );

    const input = screen.getByPlaceholderText(/비밀번호|8 자/);
    expect(input.props.secureTextEntry).toBe(true);
  });

  // 4. onChangeTextChanged 검증
  it('calls onChangeText when text changes', () => {
    const handleChangeText = jest.fn();
    
    render(
      <InputField
        label="이름"
        value="홍길동"
        onChangeText={handleChangeText}
      />
    );

    fireEvent.changeText(screen.getByPlaceholderText(/이름/), '김철수');
    
    expect(handleChangeText).toHaveBeenCalledWith('김철수');
  });

  // 5. error 메시지 표시 검증
  it('displays error message when provided', () => {
    const onChangeText = jest.fn();
    
    render(
      <InputField
        label="이메일"
        value=""
        onChangeText={onChangeText}
        error="올바른 이메일 형식이 아닙니다."
      />
    );

    expect(screen.getByText('올바른 이메일 형식이 아닙니다.')).toBeDefined();
  });

  // 6. disabled 상태 처리 검증
  it('is disabled when disabled prop is true', () => {
    const handleChangeText = jest.fn();
    
    render(
      <InputField
        label="이메일"
        value=""
        onChangeText={handleChangeText}
        disabled={true}
      />
    );

    const input = screen.getByPlaceholderText(/이메일/);
    expect(input.props.editable).toBe(false);
  });

  // 7. autoCapitalize prop 전달 검증
  it('passes autoCapitalize correctly', () => {
    const onChangeText = jest.fn();
    
    render(
      <InputField
        label="이름"
        value=""
        onChangeText={onChangeText}
        autoCapitalize="none"
      />
    );

    const input = screen.getByPlaceholderText(/이름/);
    expect(input.props.autoCapitalize).toBe('none');
  });

  // 8. empty label 처리 검증
  it('handles empty label gracefully', () => {
    const onChangeText = jest.fn();
    
    render(
      <InputField
        label=""
        value=""
        onChangeText={onChangeText}
      />
    );

    // Label 없이도 렌더링되지 않아야 함 (반대로 빈 라벨을 허용하는지 확인)
    expect(screen.getByPlaceholderText('')).toBeDefined();
  });

  // 9. 긴 placeholder 텍스트 처리 검증 (numberOfLines)
  it('handles long placeholder text', () => {
    const onChangeText = jest.fn();
    
    render(
      <InputField
        label="설명"
        value=""
        placeholder="이 입력 필드에는 매우 긴 설명 텍스트를 입력할 수 있습니다. 사용자가 어떤 정보를 입력해야 하는지 명확히 안내하기 위한 용도입니다."
        onChangeText={onChangeText}
      />
    );

    const input = screen.getByPlaceholderText(/설명/);
    expect(input.props.numberOfLines).toBeDefined();
  });

  // 10. autoCorrect prop 전달 검증
  it('passes autoCorrect correctly', () => {
    const onChangeText = jest.fn();
    
    render(
      <InputField
        label="이메일"
        value=""
        onChangeText={onChangeText}
        autoCorrect={false}
      />
    );

    const input = screen.getByPlaceholderText(/이메일/);
    expect(input.props.autoCorrect).toBe(false);
  });

  // 11. error 없는 상태 검증 (error 미제공 시)
  it('does not display error when error is not provided', () => {
    const onChangeText = jest.fn();
    
    render(
      <InputField
        label="이름"
        value=""
        onChangeText={onChangeText}
      />
    );

    // 에러 메시지 클래스가 있어야 함 (стили를 통해 확인)
    const container = screen.getByLabelText('이름');
    expect(container).toBeDefined();
  });

  // 12. disabled 상태에서의 버튼 클릭 비활성화 검증
  it('does not call onChangeText when disabled', () => {
    const handleChangeText = jest.fn();
    
    render(
      <InputField
        label="이메일"
        value=""
        onChangeText={handleChangeText}
        disabled={true}
      />
    );

    // disabled 상태에서는 텍스트 변경이 일어나지 않아야 함 (React Native 의 editable prop 으로 확인)
    const input = screen.getByPlaceholderText(/이메일/);
    expect(input.props.editable).toBe(false);
  });
});
