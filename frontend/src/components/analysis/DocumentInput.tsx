type DocumentInputProps = {
  name: 'cv' | 'jd';
  label: string;
  number: string;
  help: string;
  placeholder: string;
  value: string;
  limit?: number;
  disabled: boolean;
  onChange: (value: string) => void;
};

export function DocumentInput({
  name, label, number, help, placeholder, value, limit, disabled, onChange,
}: DocumentInputProps) {
  return (
    <div className="min-w-0">
      <div className="mb-2.5 flex items-center justify-between [&>label]:font-editorial [&>label]:text-[21px] [&>span]:text-xs [&>span]:text-[#6c786c]">
        <label htmlFor={`${name}-text`}>{label}</label>
        <span>{number}</span>
      </div>
      <p id={`${name}-help`} className="min-h-[42px] text-[13px] text-muted">{help}</p>
      <textarea
        className="min-h-[310px] w-full min-w-0 resize-y rounded border border-[#b1bcb1] bg-surface p-3 leading-[1.65] text-ink max-mobile:min-h-[250px]"
        id={`${name}-text`}
        name={`${name}-text`}
        value={value}
        onChange={event => onChange(event.target.value)}
        autoComplete="off"
        spellCheck={false}
        disabled={disabled}
        aria-describedby={`${name}-help ${name}-count`}
        placeholder={placeholder}
      />
      <span id={`${name}-count`} className="mt-1.5 block text-right text-[13px] text-[#647061]">
        {Array.from(value).length.toLocaleString('en-US')} characters
        {limit !== undefined ? ` · limit ${limit.toLocaleString('en-US')}` : ''}
      </span>
    </div>
  );
}
