import { forwardRef, type ButtonHTMLAttributes } from 'react';

type ButtonVariant = 'primary' | 'secondary' | 'text' | 'danger' | 'dangerText';
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: 'default' | 'large';
};

const variants: Record<ButtonVariant, string> = {
  primary: 'border-brand bg-brand text-white enabled:hover:bg-brand-dark',
  secondary: 'border-[#9aa9a0] bg-transparent text-brand enabled:hover:bg-[#edf1eb]',
  text: 'border-transparent bg-transparent text-brand underline underline-offset-4 enabled:hover:bg-transparent',
  danger: 'border-[#8c3b32] bg-[#8c3b32] text-white enabled:hover:bg-[#743129]',
  dangerText: 'border-transparent bg-transparent text-[#843f36] underline underline-offset-4 enabled:hover:bg-transparent',
};

// Like a shared Flutter button widget: native events and accessibility props pass through.
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'default', type = 'button', className = '', ...props },
  ref,
) {
  const spacing = variant === 'text' || variant === 'dangerText'
    ? 'px-0 py-2'
    : size === 'large' ? 'min-w-[230px] px-[26px] py-4' : 'px-5 py-[11px]';

  return (
    <button
      {...props}
      ref={ref}
      type={type}
      className={`rounded-[5px] border font-semibold leading-[1.4] disabled:cursor-not-allowed disabled:opacity-50 ${spacing} ${variants[variant]} ${className}`}
    />
  );
});
